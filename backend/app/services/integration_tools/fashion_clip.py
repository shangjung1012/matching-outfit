"""FashionCLIP adapter used to encode catalog search text and images."""

from io import BytesIO
from pathlib import Path

from app.core.config import settings


class FashionClipService:
    """Lazily loads FashionCLIP so API startup remains fast."""

    def __init__(self) -> None:
        self._model = None
        self._processor = None
        self._device = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import CLIPModel, CLIPProcessor

        self._model = CLIPModel.from_pretrained(settings.fashion_clip_model)
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        self._model.eval()
        self._processor = CLIPProcessor.from_pretrained(settings.fashion_clip_model)

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        import torch

        self._load()
        assert self._model is not None and self._processor is not None and self._device is not None
        inputs = self._processor(text=texts, return_tensors="pt", padding=True, truncation=True)
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        with torch.inference_mode():
            features = self._model.get_text_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)
        return features.cpu().tolist()

    def _encode_open_images(self, images: list[object]) -> list[list[float]]:
        import torch

        self._load()
        assert self._model is not None and self._processor is not None and self._device is not None
        inputs = self._processor(images=images, return_tensors="pt")
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        with torch.inference_mode():
            features = self._model.get_image_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)
        return features.cpu().tolist()

    def encode_images(self, paths: list[str]) -> list[list[float]]:
        """Encode catalog image files without retaining open image handles."""
        from PIL import Image, ImageOps

        images = []
        for path in paths:
            with Image.open(Path(path)) as source:
                images.append(ImageOps.exif_transpose(source).convert("RGB"))
        try:
            return self._encode_open_images(images)
        finally:
            for image in images:
                image.close()

    def encode_image_bytes(self, content: bytes) -> list[float]:
        """Encode one validated uploaded image held only in memory."""
        from PIL import Image, ImageOps

        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        try:
            return self._encode_open_images([image])[0]
        finally:
            image.close()


fashion_clip = FashionClipService()
