"""Run single-image LHM++ reconstruction without the HTTP service."""

from __future__ import annotations

import argparse
from pathlib import Path
import time
from typing import Sequence

from PIL import Image

from engine import LHMEngine
from gpu_lock import SharedGPULock


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconstruct one person as 3DGS PLY")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    if not args.image.is_file():
        raise FileNotFoundError(f"Input image does not exist: {args.image}")
    args.output.mkdir(parents=True, exist_ok=True)
    engine = LHMEngine()
    started = time.perf_counter()
    with Image.open(args.image) as source, SharedGPULock():
        result = engine.run([source.convert("RGB")], args.output)
    elapsed = time.perf_counter() - started
    peak_gib = (result.peak_gpu_memory_bytes or 0) / 1024**3
    print(f"CUDA device: {engine.device_name}", flush=True)
    print(f"Input: {args.image}", flush=True)
    print(f"Output artifact: {result.artifact_path}", flush=True)
    print(f"Elapsed: {elapsed:.2f}s", flush=True)
    print(f"Peak GPU memory: {peak_gib:.2f} GiB", flush=True)


if __name__ == "__main__":
    main()
