FROM ghcr.io/astral-sh/uv:0.9.5 AS uv

FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG LHM_COMMIT=906b5d9fb967ab42efb92f6fa55bf22cac86b653
ARG PYTORCH3D_COMMIT=978cd99221b9e0a6a568f1d427854d73363265cf
ARG DIFF_GAUSSIAN_COMMIT=8829d14f814fccdaf840b7b0f3021a616583c0a1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CUDA_HOME=/usr/local/cuda \
    TORCH_CUDA_ARCH_LIST=12.0 \
    FORCE_CUDA=1 \
    MAX_JOBS=4 \
    HF_HOME=/models/huggingface \
    HUMAN3D_PRETRAINED_DIR=/models/lhmpp/pretrained_models \
    LHM_UPSTREAM_ROOT=/opt/lhmpp

COPY --from=uv /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential curl git libegl1 libgl1 libglib2.0-0 libgomp1 \
        python3.10 python3.10-dev python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN python3.10 -m pip install --upgrade pip setuptools wheel \
    && python3.10 -m pip install \
        torch==2.8.0+cu128 torchvision==0.23.0+cu128 \
        --index-url https://download.pytorch.org/whl/cu128 \
    && python3.10 -m pip install \
        xformers==0.0.32.post2 \
        --index-url https://download.pytorch.org/whl/cu128

WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

RUN git clone https://github.com/aigc3d/LHM-plusplus.git /opt/lhmpp \
    && git -C /opt/lhmpp checkout "$LHM_COMMIT" \
    && mkdir -p /models/lhmpp/pretrained_models \
    && rm -rf /opt/lhmpp/pretrained_models \
    && ln -s /models/lhmpp/pretrained_models /opt/lhmpp/pretrained_models

# Build every active CUDA extension for Blackwell (sm_120); no legacy wheels are used.
RUN python3.10 -m pip install gsplat==1.5.3 \
    && python3.10 -m pip install \
        "git+https://github.com/facebookresearch/pytorch3d.git@${PYTORCH3D_COMMIT}" \
        --no-build-isolation \
    && python3.10 -m pip install /opt/lhmpp/lib/pointops --no-build-isolation \
    && python3.10 -m pip install \
        "git+https://github.com/ashawkey/diff-gaussian-rasterization.git@${DIFF_GAUSSIAN_COMMIT}" \
        --no-build-isolation

COPY . .

EXPOSE 9002
CMD ["python3.10", "-m", "uvicorn", "service:app", "--host", "0.0.0.0", "--port", "9002"]
