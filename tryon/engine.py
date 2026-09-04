from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image


REFERENCE_TYPES = ("upper", "lower", "overall", "shoe", "bag")
PERSON_SIZE = (768, 1024)
REFERENCE_SIZE = (384, 512)


def center_crop_to_aspect_ratio(image: Image.Image, ratio: float) -> Image.Image:
    width, height = image.size
    if width / height > ratio:
        crop_width = int(height * ratio)
        left = (width - crop_width) // 2
        return image.crop((left, 0, left + crop_width, height))
    crop_height = int(width / ratio)
    top = (height - crop_height) // 2
    return image.crop((0, top, width, top + crop_height))


class FastFitEngine:
    def __init__(
        self,
        *,
        pipeline: Any | None = None,
        dwpose_detector: Any | None = None,
        densepose_detector: Any | None = None,
        schp_lip_detector: Any | None = None,
        schp_atr_detector: Any | None = None,
        mask_builder: Callable[..., Image.Image] | None = None,
        torch_module: Any | None = None,
        snapshot_downloader: Callable[..., str] | None = None,
        pipeline_factory: Callable[..., Any] | None = None,
        dwpose_factory: Callable[..., Any] | None = None,
        densepose_factory: Callable[..., Any] | None = None,
        schp_factory: Callable[..., Any] | None = None,
    ) -> None:
        if torch_module is None:
            import torch

            torch_module = torch
        self.torch = torch_module
        if not self.torch.cuda.is_available():
            raise RuntimeError("FastFit requires an NVIDIA CUDA GPU")
        self.device_name = self.torch.cuda.get_device_name(0)

        components = (
            pipeline,
            dwpose_detector,
            densepose_detector,
            schp_lip_detector,
            schp_atr_detector,
            mask_builder,
        )
        if any(component is None for component in components):
            if snapshot_downloader is None:
                from huggingface_hub import snapshot_download

                snapshot_downloader = snapshot_download
            fastfit_path = snapshot_downloader(
                repo_id="zhengchong/FastFit-MR-1024",
            )
            toolkit_path = snapshot_downloader(
                repo_id="zhengchong/Human-Toolkit",
                allow_patterns=["DWPose/*", "DensePose/*", "SCHP/*"],
            )

            if any(
                factory is None
                for factory in (
                    pipeline_factory,
                    dwpose_factory,
                    densepose_factory,
                    schp_factory,
                )
            ) or mask_builder is None:
                from fastfit.module.pipeline_fastfit import FastFitPipeline
                from fastfit.parse_utils import (
                    DWposeDetector,
                    DensePose,
                    SCHP,
                    multi_ref_cloth_agnostic_mask,
                )

                pipeline_factory = pipeline_factory or FastFitPipeline
                dwpose_factory = dwpose_factory or DWposeDetector
                densepose_factory = densepose_factory or DensePose
                schp_factory = schp_factory or SCHP
                mask_builder = mask_builder or multi_ref_cloth_agnostic_mask

            pipeline = pipeline or pipeline_factory(
                base_model_path=fastfit_path,
                device="cuda",
                mixed_precision=os.getenv("TRYON_MIXED_PRECISION", "bf16"),
                allow_tf32=True,
            )
            dwpose_detector = dwpose_detector or dwpose_factory(
                pretrained_model_name_or_path=str(Path(toolkit_path) / "DWPose"),
                device="cpu",
            )
            densepose_detector = densepose_detector or densepose_factory(
                model_path=str(Path(toolkit_path) / "DensePose"),
                device="cuda",
            )
            schp_lip_detector = schp_lip_detector or schp_factory(
                ckpt_path=str(Path(toolkit_path) / "SCHP" / "schp-lip.pth"),
                device="cuda",
            )
            schp_atr_detector = schp_atr_detector or schp_factory(
                ckpt_path=str(Path(toolkit_path) / "SCHP" / "schp-atr.pth"),
                device="cuda",
            )

        self.pipeline = pipeline
        self.dwpose_detector = dwpose_detector
        self.densepose_detector = densepose_detector
        self.schp_lip_detector = schp_lip_detector
        self.schp_atr_detector = schp_atr_detector
        self.mask_builder = mask_builder

    def run(
        self,
        person: Image.Image,
        references: dict[str, Image.Image],
    ) -> bytes:
        if not references:
            raise ValueError("At least one reference image is required")
        unknown_types = set(references) - set(REFERENCE_TYPES)
        if unknown_types:
            raise ValueError(f"Unsupported reference type: {sorted(unknown_types)[0]}")
        if "overall" in references and (
            "upper" in references or "lower" in references
        ):
            raise ValueError("overall cannot be combined with upper or lower")

        person = center_crop_to_aspect_ratio(person.convert("RGB"), 3 / 4)
        person = person.resize(PERSON_SIZE, Image.Resampling.LANCZOS)
        pose = self.dwpose_detector(person)
        if not isinstance(pose, Image.Image):
            raise RuntimeError("Pose estimation failed")

        densepose = np.asarray(self.densepose_detector(person))
        lip = np.asarray(self.schp_lip_detector(person))
        atr = np.asarray(self.schp_atr_detector(person))
        mask = self.mask_builder(
            densepose,
            lip,
            atr,
            square_cloth_mask=False,
            horizon_expand=True,
        )

        ref_images: list[Image.Image] = []
        ref_attention_masks: list[int] = []
        for reference_type in REFERENCE_TYPES:
            reference = references.get(reference_type)
            if reference is None:
                ref_images.append(Image.new("RGB", REFERENCE_SIZE, "black"))
                ref_attention_masks.append(0)
            else:
                ref_images.append(
                    reference.convert("RGB").resize(
                        REFERENCE_SIZE,
                        Image.Resampling.LANCZOS,
                    )
                )
                ref_attention_masks.append(1)

        generator = self.torch.Generator(device="cuda").manual_seed(42)
        with self.torch.no_grad():
            result = self.pipeline(
                person=person,
                mask=mask,
                ref_images=ref_images,
                ref_labels=list(REFERENCE_TYPES),
                ref_attention_masks=ref_attention_masks,
                pose=pose,
                num_inference_steps=50,
                guidance_scale=2.5,
                generator=generator,
                return_pil=True,
            )
        if not result or not isinstance(result[0], Image.Image):
            raise RuntimeError("FastFit returned no image")

        image = result[0].convert("RGB")
        if image.size != PERSON_SIZE:
            image = image.resize(PERSON_SIZE, Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
