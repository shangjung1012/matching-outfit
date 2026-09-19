from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import gc
import importlib.util
import os
from pathlib import Path
import sys
from threading import RLock
from typing import Any, Iterator

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ReconstructionResult:
    artifact_path: Path
    artifact_format: str
    preview_path: Path | None = None
    peak_gpu_memory_bytes: int | None = None


@contextmanager
def working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class LHMEngine:
    """Stable wrapper around the pinned official LHM++ PLY export path."""

    REQUIRED_IMPORTS = (
        "addict",
        "chumpy",
        "diff_gaussian_rasterization",
        "gsplat",
        "pointops_cuda",
        "pytorch3d",
        "spconv.pytorch",
        "torch_scatter",
        "xformers",
    )

    def __init__(
        self,
        *,
        torch_module: Any | None = None,
        upstream_root: Path | None = None,
        model_name: str | None = None,
        model_path: Path | None = None,
    ) -> None:
        if torch_module is None:
            import torch

            torch_module = torch
        self.torch = torch_module
        if not self.torch.cuda.is_available():
            raise RuntimeError("LHM++ requires an NVIDIA CUDA GPU; CPU fallback is disabled")
        self.device_name = self.torch.cuda.get_device_name(0)
        capability = self.torch.cuda.get_device_capability(0)
        self.cuda_capability = f"{capability[0]}.{capability[1]}"
        self.upstream_root = Path(
            upstream_root or os.getenv("LHM_UPSTREAM_ROOT", "/opt/lhmpp")
        ).resolve()
        self.model_name = model_name or os.getenv(
            "HUMAN3D_MODEL_ID", "LHMPP-700M-PixelShuffle"
        )
        configured_path = model_path or os.getenv("HUMAN3D_MODEL_PATH", "")
        self.model_path = Path(configured_path).resolve() if configured_path else None
        self.device = "cuda:0"
        self._model: Any | None = None
        self._cfg: Any | None = None
        self._upstream: Any | None = None
        self._rembg_session: Any | None = None
        self._lock = RLock()
        self.peak_gpu_memory_bytes = 0
        self.model_gpu_memory_bytes = 0

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def _import_upstream_export(self) -> Any:
        if self._upstream is not None:
            return self._upstream
        script = self.upstream_root / "scripts" / "inference" / "to_gs_ply.py"
        if not script.is_file():
            raise RuntimeError(f"Pinned LHM++ checkout is missing: {script}")
        root = str(self.upstream_root)
        if root not in sys.path:
            sys.path.insert(0, root)
        spec = importlib.util.spec_from_file_location("matching_outfit_lhmpp_export", script)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot import LHM++ export module from {script}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._upstream = module
        return module

    def _check_dependencies(self) -> None:
        missing = []
        for name in self.REQUIRED_IMPORTS:
            try:
                available = importlib.util.find_spec(name) is not None
            except (ImportError, AttributeError, ValueError):
                # find_spec("package.module") imports the parent package and
                # raises when that parent is missing instead of returning None.
                available = False
            if not available:
                missing.append(name)
        if missing:
            raise RuntimeError(
                "Required Human3D dependencies are unavailable: " + ", ".join(missing)
            )

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            self._check_dependencies()
            upstream = self._import_upstream_export()
            os.environ.update(
                {
                    "APP_ENABLED": "1",
                    "APP_MODEL_NAME": self.model_name,
                    "APP_TYPE": "infer.human_lrm_a4o",
                    "NUMBA_THREADING_LAYER": "omp",
                }
            )
            pretrained_dir = Path(
                os.getenv("HUMAN3D_PRETRAINED_DIR", "/models/lhmpp/pretrained_models")
            ).resolve()
            pretrained_dir.mkdir(parents=True, exist_ok=True)
            with working_directory(self.upstream_root):
                upstream._require_gs_output_model(self.model_name)
                upstream.prior_model_check(save_dir=str(pretrained_dir))
                if self.model_path is not None:
                    model_path = self.model_path
                else:
                    query = upstream.AutoModelQuery(save_dir=str(pretrained_dir))
                    model_path = Path(query.query(self.model_name))
                config_path = Path(upstream.MODEL_CONFIG[self.model_name])
                if not config_path.is_absolute():
                    config_path = self.upstream_root / config_path
                cards = {
                    self.model_name: {
                        "model_path": str(model_path),
                        "model_config": str(config_path),
                    }
                }
                _ = upstream.Accelerator()
                cfg, _ = upstream.parse_app_configs(cards)
                model = upstream.build_app_model(cfg)
                model.eval()
                model.to(self.device)
            self._cfg = cfg
            self._model = model
            self.model_gpu_memory_bytes = int(self.torch.cuda.memory_allocated(0))

    def unload(self) -> None:
        with self._lock:
            model = self._model
            self._model = None
            self._cfg = None
            if model is not None:
                model.to("cpu")
                del model
            gc.collect()
            self.torch.cuda.empty_cache()
            ipc_collect = getattr(self.torch.cuda, "ipc_collect", None)
            if callable(ipc_collect):
                ipc_collect()
            self.model_gpu_memory_bytes = 0

    def _segment_and_frame(self, image: Image.Image) -> Image.Image:
        import rembg

        if self._rembg_session is None:
            self._rembg_session = rembg.new_session(
                "u2net_human_seg",
                providers=["CPUExecutionProvider"],
            )
        rgb = np.asarray(image.convert("RGB"))
        rgba = np.asarray(rembg.remove(rgb, session=self._rembg_session))
        if rgba.ndim != 3 or rgba.shape[2] < 4:
            raise RuntimeError("Foreground segmentation returned no alpha mask")
        alpha = rgba[..., 3]
        rows, columns = np.nonzero(alpha > 16)
        if not len(rows) or not len(columns):
            raise ValueError("No person was found in the input image")
        top, bottom = int(rows.min()), int(rows.max()) + 1
        left, right = int(columns.min()), int(columns.max()) + 1
        crop = Image.fromarray(rgba).crop((left, top, right, bottom))
        target = 512
        content_size = int(target * 0.84)
        scale = min(content_size / crop.width, content_size / crop.height)
        resized = crop.resize(
            (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGBA", (target, target), (255, 255, 255, 255))
        offset = ((target - resized.width) // 2, (target - resized.height) // 2)
        canvas.alpha_composite(resized, offset)
        return canvas.convert("RGB")

    def run(self, images: list[Image.Image], output_dir: Path) -> ReconstructionResult:
        if not images:
            raise ValueError("At least one image is required")
        if len(images) > 8:
            raise ValueError("At most eight input views are supported")
        with self._lock:
            self.load()
            assert self._model is not None and self._cfg is not None
            output_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = output_dir / "result.ply"
            artifact_path.unlink(missing_ok=True)
            prepared = [np.asarray(self._segment_and_frame(image)) for image in images]
            ref_tensor = (
                self.torch.from_numpy(np.stack(prepared) / 255.0)
                .permute(0, 3, 1, 2)
                .float()
                .to(self.device)
            )
            motion = self._upstream._build_synthetic_motion_seq(self._cfg)
            self.torch.cuda.reset_peak_memory_stats(0)
            precision = os.getenv("HUMAN3D_MIXED_PRECISION", "bf16").lower()
            autocast = (
                self.torch.autocast(
                    device_type="cuda",
                    dtype=self.torch.bfloat16,
                )
                if precision == "bf16"
                else nullcontext()
            )
            try:
                with self.torch.inference_mode(), autocast, working_directory(
                    self.upstream_root
                ):
                    self._upstream.run_tpose_export(
                        self._model,
                        ref_tensor,
                        motion,
                        device=self.device,
                        output_ply=str(artifact_path),
                        export_animation_pose=False,
                    )
            except Exception:
                artifact_path.unlink(missing_ok=True)
                raise
            finally:
                del ref_tensor
            if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
                raise RuntimeError("LHM++ did not produce a Gaussian Splat PLY")
            peak = int(self.torch.cuda.max_memory_allocated(0))
            self.peak_gpu_memory_bytes = max(self.peak_gpu_memory_bytes, peak)
            return ReconstructionResult(
                artifact_path=artifact_path,
                artifact_format="ply",
                peak_gpu_memory_bytes=peak,
            )
