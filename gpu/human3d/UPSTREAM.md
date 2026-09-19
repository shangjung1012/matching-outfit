# LHM++ upstream and compatibility notes

This service calls the official [aigc3d/LHM-plusplus](https://github.com/aigc3d/LHM-plusplus)
implementation. The Docker build checks out commit
`906b5d9fb967ab42efb92f6fa55bf22cac86b653` (2026-05-29). It does not vendor or
rewrite the model. `engine.py` wraps the upstream `infer_single_view` →
`inference_gs` → `GaussianModel.save_ply` path from
`scripts/inference/to_gs_ply.py`.

The default checkpoint is `LHMPP-700M-PixelShuffle`, downloaded by the upstream
`AutoModelQuery` into the persistent model volume. `LHMPP-700M-SMPLX-FREE` is
also accepted because it is in upstream's `GS_RENDER_SUPPORTED_MODEL_NAMES`.
Both export standard INRIA-style 3D Gaussian Splat PLY files.

## RTX 5080 changes

Upstream's documented environment (PyTorch 2.3/CUDA 12.1, gsplat 1.4) predates
Blackwell. This image intentionally uses Python 3.10, PyTorch 2.8.0 + CUDA
12.8, xFormers 0.0.32.post2, and gsplat 1.5.3. PyTorch 2.7 was the first release
with Blackwell and CUDA 12.8 wheels; gsplat 1.4 predates `sm_120` support.
PointOps, PyTorch3D, and diff-gaussian-rasterization are built from source with
`TORCH_CUDA_ARCH_LIST=12.0`. `spconv`, `torch-scatter`, `simple-knn`, and
flash-attn are not installed because the selected PixelShuffle inference/export
path does not import or execute them. There is no CPU fallback.

Pinned extension sources:

- PyTorch3D: `978cd99221b9e0a6a568f1d427854d73363265cf`
- diff-gaussian-rasterization: `8829d14f814fccdaf840b7b0f3021a616583c0a1`
- gsplat: `1.5.3`

At startup the engine checks CUDA availability, device name/capability, and the
five active extension imports. `/health` reports initialization failures rather
than claiming the model is ready.

## Licenses

LHM++ source is Apache License 2.0 (`LICENSE` upstream). Model weights are
separately licensed under Creative Commons Attribution-NonCommercial 4.0
(`LICENSE_WEIGHT` upstream): research/non-commercial use only, with attribution.
The checkpoint remains owned and distributed by its upstream authors and is
not part of this repository. NVIDIA components retain their own licenses.
