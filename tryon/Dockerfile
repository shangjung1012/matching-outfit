FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install \
    torch==2.14.0+cu130 \
    torchvision==0.29.0+cu130 \
    --index-url https://download.pytorch.org/whl/cu130 \
    --extra-index-url https://pypi.org/simple

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 9001

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "9001"]
