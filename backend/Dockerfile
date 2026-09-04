# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=300

# PyTorch 獨立安裝，避免一般套件查詢 PyTorch index
COPY requirements-torch.txt .

RUN --mount=type=cache,id=pip-cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install \
    --retries 10 \
    -r requirements-torch.txt

# 其餘套件只從 PyPI 安裝
COPY requirements.txt .

RUN --mount=type=cache,id=pip-cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install \
    --index-url https://pypi.org/simple \
    --retries 5 \
    -r requirements.txt

# 最後才複製程式碼，避免改程式就重新安裝依賴
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]