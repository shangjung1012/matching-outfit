"""FashionCLIP adapter used to encode catalog search text and images."""

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

    def encode_images(self, paths: list[str]) -> list[list[float]]:
        import torch
        from PIL import Image

        self._load()
        assert self._model is not None and self._processor is not None and self._device is not None
        images = [Image.open(Path(path)).convert("RGB") for path in paths]
        try:
            inputs = self._processor(images=images, return_tensors="pt")
            inputs = {key: value.to(self._device) for key, value in inputs.items()}
            with torch.inference_mode():
                features = self._model.get_image_features(**inputs)
                features = features / features.norm(dim=-1, keepdim=True)
            return features.cpu().tolist()
        finally:
            for image in images:
                image.close()


fashion_clip = FashionClipService()
