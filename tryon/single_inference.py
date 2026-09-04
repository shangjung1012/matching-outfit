"""Run FastFit on a person image and one or more reference images."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from PIL import Image

from engine import FastFitEngine, REFERENCE_TYPES


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run FastFit virtual try-on with one or more references."
    )
    parser.add_argument("--person", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    for reference_type in REFERENCE_TYPES:
        parser.add_argument(f"--{reference_type}", type=Path)
    args = parser.parse_args(argv)

    reference_types = [
        reference_type
        for reference_type in REFERENCE_TYPES
        if getattr(args, reference_type) is not None
    ]
    if not reference_types:
        parser.error("at least one reference image is required")
    if "overall" in reference_types and (
        "upper" in reference_types or "lower" in reference_types
    ):
        parser.error("--overall cannot be combined with --upper or --lower")
    return args


def main() -> None:
    args = parse_args()
    input_paths = [args.person]
    input_paths.extend(
        getattr(args, reference_type)
        for reference_type in REFERENCE_TYPES
        if getattr(args, reference_type) is not None
    )
    for image_path in input_paths:
        if not image_path.is_file():
            raise FileNotFoundError(f"Input image does not exist: {image_path}")

    references = {
        reference_type: Image.open(getattr(args, reference_type)).convert("RGB")
        for reference_type in REFERENCE_TYPES
        if getattr(args, reference_type) is not None
    }
    person = Image.open(args.person).convert("RGB")
    engine = FastFitEngine()
    result = engine.run(person, references)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    print(f"CUDA device: {engine.device_name}", flush=True)
    print(f"Saved result: {args.output}", flush=True)


if __name__ == "__main__":
    main()
