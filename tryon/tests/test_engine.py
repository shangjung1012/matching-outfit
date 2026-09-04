from __future__ import annotations

from contextlib import nullcontext
from io import BytesIO

import numpy as np
from PIL import Image
import pytest

import engine


class FakeCuda:
    def __init__(self, available: bool = True) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available

    def get_device_name(self, index: int) -> str:
        assert index == 0
        return "Fake RTX"


class FakeGenerator:
    def __init__(self, device: str) -> None:
        self.device = device
        self.seed: int | None = None

    def manual_seed(self, seed: int) -> "FakeGenerator":
        self.seed = seed
        return self


class FakeTorch:
    def __init__(self, cuda_available: bool = True) -> None:
        self.cuda = FakeCuda(cuda_available)

    def Generator(self, device: str) -> FakeGenerator:
        return FakeGenerator(device)

    def no_grad(self):
        return nullcontext()


class RecordingDetector:
    def __init__(self, result: Image.Image) -> None:
        self.result = result
        self.inputs: list[Image.Image] = []

    def __call__(self, image: Image.Image) -> Image.Image:
        self.inputs.append(image.copy())
        return self.result


class RecordingPipeline:
    def __init__(self) -> None:
        self.call: dict | None = None

    def __call__(self, **kwargs):
        self.call = kwargs
        return [Image.new("RGB", (600, 800), "purple")]


def test_engine_preprocesses_person_and_calls_pipeline_with_five_slots() -> None:
    pose = Image.new("RGB", (768, 1024), "cyan")
    densepose = RecordingDetector(Image.new("L", (768, 1024), 1))
    lip = RecordingDetector(Image.new("L", (768, 1024), 2))
    atr = RecordingDetector(Image.new("L", (768, 1024), 3))
    dwpose = RecordingDetector(pose)
    pipeline = RecordingPipeline()
    mask_calls: list[tuple[np.ndarray, np.ndarray, np.ndarray, dict]] = []

    def build_mask(densepose_arr, lip_arr, atr_arr, **kwargs):
        mask_calls.append((densepose_arr, lip_arr, atr_arr, kwargs))
        return Image.new("L", (768, 1024), 255)

    runtime = FakeTorch()
    fastfit = engine.FastFitEngine(
        pipeline=pipeline,
        dwpose_detector=dwpose,
        densepose_detector=densepose,
        schp_lip_detector=lip,
        schp_atr_detector=atr,
        mask_builder=build_mask,
        torch_module=runtime,
    )

    person = Image.new("RGB", (1200, 800), "green")
    for x in range(300):
        for y in range(800):
            person.putpixel((x, y), (255, 0, 0))
            person.putpixel((1199 - x, y), (0, 0, 255))
    result_bytes = fastfit.run(
        person,
        {
            "bag": Image.new("RGB", (60, 40), "yellow"),
            "upper": Image.new("RGB", (40, 60), "red"),
        },
    )

    assert fastfit.device_name == "Fake RTX"
    assert [item.inputs[0].size for item in (dwpose, densepose, lip, atr)] == [
        (768, 1024),
    ] * 4
    assert all(
        item.inputs[0].getpixel((0, 0)) == (0, 128, 0)
        for item in (dwpose, densepose, lip, atr)
    )
    assert len(mask_calls) == 1
    assert [array.shape for array in mask_calls[0][:3]] == [
        (1024, 768),
        (1024, 768),
        (1024, 768),
    ]
    assert mask_calls[0][3] == {
        "square_cloth_mask": False,
        "horizon_expand": True,
    }

    call = pipeline.call
    assert call is not None
    assert call["person"].size == (768, 1024)
    assert call["person"].getpixel((0, 0)) == (0, 128, 0)
    assert call["mask"].size == (768, 1024)
    assert call["pose"] is pose
    assert call["ref_labels"] == ["upper", "lower", "overall", "shoe", "bag"]
    assert call["ref_attention_masks"] == [1, 0, 0, 0, 1]
    assert [image.size for image in call["ref_images"]] == [(384, 512)] * 5
    assert call["ref_images"][0].getpixel((0, 0)) == (255, 0, 0)
    assert [call["ref_images"][index].getbbox() for index in (1, 2, 3)] == [
        None,
    ] * 3
    assert call["ref_images"][4].getpixel((0, 0)) == (255, 255, 0)
    assert call["num_inference_steps"] == 50
    assert call["guidance_scale"] == 2.5
    assert call["generator"].device == "cuda"
    assert call["generator"].seed == 42
    assert call["return_pil"] is True

    with Image.open(BytesIO(result_bytes)) as result:
        assert result.format == "PNG"
        assert result.size == (768, 1024)


def test_engine_rejects_non_cuda_before_downloading() -> None:
    downloads: list[dict] = []
    with pytest.raises(RuntimeError, match="CUDA"):
        engine.FastFitEngine(
            torch_module=FakeTorch(cuda_available=False),
            snapshot_downloader=lambda **kwargs: downloads.append(kwargs),
        )
    assert downloads == []


def test_engine_downloads_only_required_human_toolkit_trees() -> None:
    downloads: list[dict] = []
    factory_calls: dict[str, list[dict]] = {
        "pipeline": [],
        "dwpose": [],
        "densepose": [],
        "schp": [],
    }

    def download(**kwargs):
        downloads.append(kwargs)
        return "/cache/fastfit" if len(downloads) == 1 else "/cache/toolkit"

    def factory(name):
        def create(**kwargs):
            factory_calls[name].append(kwargs)
            return object()

        return create

    engine.FastFitEngine(
        torch_module=FakeTorch(),
        snapshot_downloader=download,
        pipeline_factory=factory("pipeline"),
        dwpose_factory=factory("dwpose"),
        densepose_factory=factory("densepose"),
        schp_factory=factory("schp"),
        mask_builder=lambda *_args, **_kwargs: None,
    )

    assert downloads == [
        {"repo_id": "zhengchong/FastFit-MR-1024"},
        {
            "repo_id": "zhengchong/Human-Toolkit",
            "allow_patterns": ["DWPose/*", "DensePose/*", "SCHP/*"],
        },
    ]
    assert factory_calls == {
        "pipeline": [
            {
                "base_model_path": "/cache/fastfit",
                "device": "cuda",
                "mixed_precision": "bf16",
                "allow_tf32": True,
            }
        ],
        "dwpose": [
            {
                "pretrained_model_name_or_path": "/cache/toolkit/DWPose",
                "device": "cpu",
            }
        ],
        "densepose": [
            {"model_path": "/cache/toolkit/DensePose", "device": "cuda"}
        ],
        "schp": [
            {"ckpt_path": "/cache/toolkit/SCHP/schp-lip.pth", "device": "cuda"},
            {"ckpt_path": "/cache/toolkit/SCHP/schp-atr.pth", "device": "cuda"},
        ],
    }
