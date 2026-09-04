"""Run CatVTON on one person image and one garment image."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import torch
from diffusers.image_processor import VaeImageProcessor
from huggingface_hub import snapshot_download
from PIL import Image

from model.cloth_masker import AutoMasker
from model.pipeline import CatVTONPipeline
from utils import init_weight_dtype, resize_and_crop, resize_and_padding


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run CatVTON virtual try-on with a person and garment image."
    )
    parser.add_argument("--person", type=Path, required=True)
    parser.add_argument("--cloth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cloth-type",
        default="upper",
        choices=["upper", "lower", "overall", "inner", "outer"],
    )
    parser.add_argument(
        "--base-model-path",
        default="booksforcharlie/stable-diffusion-inpainting",
    )
    parser.add_argument("--resume-path", default="zhengchong/CatVTON")
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--guidance-scale", type=float, default=2.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--mixed-precision",
        default="bf16",
        choices=["no", "fp16", "bf16"],
    )
    parser.add_argument(
        "--skip-safety-check",
        action="store_true",
        help="Disable the Stable Diffusion safety checker.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CatVTON requires a CUDA GPU for this inference script.")
    for image_path in (args.person, args.cloth):
        if not image_path.is_file():
            raise FileNotFoundError(f"Input image does not exist: {image_path}")
    if args.width % 8 or args.height % 8:
        raise ValueError("--width and --height must both be multiples of 8.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    mask_output = args.output.with_name(f"{args.output.stem}_mask.png")

    print(f"CUDA device: {torch.cuda.get_device_name(0)}", flush=True)
    print(f"Person: {args.person}", flush=True)
    print(f"Cloth: {args.cloth}", flush=True)
    print(f"Cloth type: {args.cloth_type}", flush=True)

    repo_path = snapshot_download(repo_id=args.resume_path)
    weight_dtype = init_weight_dtype(args.mixed_precision)

    pipeline = CatVTONPipeline(
        base_ckpt=args.base_model_path,
        attn_ckpt=repo_path,
        attn_ckpt_version="mix",
        weight_dtype=weight_dtype,
        use_tf32=True,
        device="cuda",
        skip_safety_check=args.skip_safety_check,
    )
    automasker = AutoMasker(
        densepose_ckpt=os.path.join(repo_path, "DensePose"),
        schp_ckpt=os.path.join(repo_path, "SCHP"),
        device="cuda",
    )
    mask_processor = VaeImageProcessor(
        vae_scale_factor=8,
        do_normalize=False,
        do_binarize=True,
        do_convert_grayscale=True,
    )

    person_image = Image.open(args.person).convert("RGB")
    cloth_image = Image.open(args.cloth).convert("RGB")
    person_image = resize_and_crop(person_image, (args.width, args.height))
    cloth_image = resize_and_padding(cloth_image, (args.width, args.height))

    mask = automasker(person_image, args.cloth_type)["mask"]
    mask = mask_processor.blur(mask, blur_factor=9)
    mask.save(mask_output)

    generator = torch.Generator(device="cuda").manual_seed(args.seed)
    result = pipeline(
        image=person_image,
        condition_image=cloth_image,
        mask=mask,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance_scale,
        generator=generator,
        width=args.width,
        height=args.height,
    )[0]
    result.save(args.output)

    print(f"Saved result: {args.output}", flush=True)
    print(f"Saved mask: {mask_output}", flush=True)


if __name__ == "__main__":
    main()
