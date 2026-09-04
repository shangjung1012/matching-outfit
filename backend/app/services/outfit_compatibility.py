"""Optional Dressify image-compatibility reranker.

The model ranks completed outfits only.  It never changes catalog retrieval or the
existing Outfit Ranker score, and safely falls back to that ordering when unavailable.
"""

from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from app.schemas import OutfitRecommendation


class CompatibilityUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _models():
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as functional
        import torchvision.models as models
        from huggingface_hub import hf_hub_download
    except ImportError as error:
        raise CompatibilityUnavailable("torchvision or huggingface-hub is not installed") from error

    class ItemEmbedder(nn.Module):
        def __init__(self):
            super().__init__()
            base = models.resnet50(weights=None)
            self.backbone = nn.Sequential(*list(base.children())[:-1])
            self.proj = nn.Linear(2048, 512)
        def forward(self, images):
            return functional.normalize(self.proj(self.backbone(images).flatten(1)), p=2, dim=1)

    class OutfitModel(nn.Module):
        def __init__(self):
            super().__init__()
            layer = nn.TransformerEncoderLayer(512, 8, 2048, 0.1, batch_first=True, activation="gelu", norm_first=True)
            self.encoder = nn.TransformerEncoder(layer, 4)
            self.head = nn.Sequential(nn.LayerNorm(512), nn.Linear(512, 256), nn.GELU(), nn.Linear(256, 1))
        def forward(self, items):
            return self.head(self.encoder(items).mean(dim=1)).squeeze(-1)

    def state(path: str):
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        values = checkpoint.get("state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
        return {key.removeprefix("module."): value for key, value in values.items()}

    item = ItemEmbedder()
    outfit = OutfitModel()
    item.load_state_dict(state(hf_hub_download("Stylique/dressify-models", "resnet_item_embedder_best.pth")), strict=False)
    outfit.load_state_dict(state(hf_hub_download("Stylique/dressify-models", "vit_outfit_model_best.pth")), strict=False)
    return torch, item.eval(), outfit.eval()


def rerank_outfits_by_compatibility(outfits: list[OutfitRecommendation]) -> tuple[list[OutfitRecommendation], str]:
    """Rank valid image groups by Dressify raw score; retain all fallback candidates."""
    if not outfits:
        return [], "no candidates"
    try:
        torch, item_model, outfit_model = _models()
        from PIL import Image
        import torchvision.transforms as transforms
        transform = transforms.Compose([transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BICUBIC), transforms.ToTensor(), transforms.Normalize([.485, .456, .406], [.229, .224, .225])])
        groups: dict[int, list[OutfitRecommendation]] = defaultdict(list)
        skipped: list[OutfitRecommendation] = []
        for outfit in outfits:
            if all(item.image_path and Path(item.image_path).is_file() for item in outfit.items):
                groups[len(outfit.items)].append(outfit)
            else:
                skipped.append(outfit)
        scored: list[tuple[float, OutfitRecommendation]] = []
        with torch.inference_mode():
            for _, batch in groups.items():
                paths = list(dict.fromkeys(path for outfit in batch for path in [item.image_path for item in outfit.items] if path))
                tensors = []
                for path in paths:
                    with Image.open(path) as image:
                        tensors.append(transform(image.convert("RGB")))
                embeddings = item_model(torch.stack(tensors))
                by_path = dict(zip(paths, embeddings, strict=True))
                input_batch = torch.stack([torch.stack([by_path[item.image_path] for item in outfit.items]) for outfit in batch])
                scores = outfit_model(input_batch).tolist()
                scored.extend(zip(scores, batch, strict=True))
        scored.sort(key=lambda value: value[0], reverse=True)
        return [outfit for _, outfit in scored] + skipped, f"scored {len(scored)} outfits; fallback {len(skipped)}"
    except Exception as error:
        return outfits, f"fallback: {error}"
