"""Image-to-catalog clothes similarity search pipeline."""

from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.cloth import Cloth
from app.schemas.try_on import TryOnReferenceType
from app.schemas.workflow import GarmentZone, SimilarCatalogItem
from app.services.integration_tools.fashion_clip import fashion_clip


SHOE_ARTICLE_TYPES = {
    "shoe", "shoes", "boot", "boots", "sneaker", "sneakers", "sandal",
    "sandals", "pumps", "slippers", "heels", "footwear", "wedges",
    "booties", "flip flops",
}
BAG_ARTICLE_TYPES = {
    "bag", "bags", "handbag", "handbags", "backpack", "backpacks", "purse",
    "purses", "tote", "totes", "clutch", "clutches",
}


def reference_type_for_cloth(cloth: Cloth) -> TryOnReferenceType | None:
    if cloth.garment_zone == "upper_body":
        return "upper"
    if cloth.garment_zone == "lower_body":
        return "lower"
    if cloth.garment_zone == "one_piece":
        return "overall"
    if cloth.garment_zone != "accessory":
        return None

    sub_category = (cloth.sub_category or "").strip().lower()
    article_type = (cloth.article_type or "").strip().lower()
    if sub_category == "bags" or article_type in BAG_ARTICLE_TYPES:
        return "bag"
    if sub_category == "shoes" or article_type in SHOE_ARTICLE_TYPES:
        return "shoe"
    return None


def _reference_type_conditions(reference_type: TryOnReferenceType) -> list:
    if reference_type == "upper":
        return [Cloth.garment_zone == "upper_body"]
    if reference_type == "lower":
        return [Cloth.garment_zone == "lower_body"]
    if reference_type == "overall":
        return [Cloth.garment_zone == "one_piece"]
    article_types = SHOE_ARTICLE_TYPES if reference_type == "shoe" else BAG_ARTICLE_TYPES
    sub_category = "shoes" if reference_type == "shoe" else "bags"
    return [
        Cloth.garment_zone == "accessory",
        or_(
            func.lower(Cloth.sub_category) == sub_category,
            func.lower(Cloth.article_type).in_(article_types),
        ),
    ]


def _similar_item(cloth: Cloth, raw_distance: float) -> SimilarCatalogItem:
    similarity = max(0.0, min(1.0, 1.0 - float(raw_distance)))
    return SimilarCatalogItem(
        id=cloth.id,
        source_item_id=cloth.source_item_id,
        product_display_name=cloth.product_display_name,
        garment_zone=cloth.garment_zone,
        image_url=cloth.image_url,
        price=cloth.price,
        original_price=cloth.original_price,
        discounted_price=cloth.discounted_price,
        currency=cloth.currency,
        brand_name=cloth.brand_name,
        age_group=cloth.age_group,
        gender=cloth.gender,
        master_category=cloth.master_category,
        sub_category=cloth.sub_category,
        article_type=cloth.article_type,
        base_colour=cloth.base_colour,
        season=cloth.season,
        year=cloth.year,
        usage=cloth.usage,
        has_embedding=cloth.embedding is not None,
        similarity=round(similarity, 4),
    )


def _find_similar(
    db: Session,
    embedding: list[float],
    *,
    limit: int,
    garment_type: GarmentZone | None = None,
    reference_type: TryOnReferenceType | None = None,
    exclude_id: int | None = None,
) -> list[SimilarCatalogItem]:
    distance = Cloth.embedding.cosine_distance(embedding).label("distance")
    conditions = [Cloth.embedding.is_not(None)]
    if reference_type is not None:
        conditions.extend(_reference_type_conditions(reference_type))
    elif garment_type is not None:
        conditions.append(Cloth.garment_zone == garment_type)
    if exclude_id is not None:
        conditions.append(Cloth.id != exclude_id)
    rows = db.execute(
        select(Cloth, distance).where(*conditions).order_by(distance).limit(limit)
    ).all()
    return [_similar_item(cloth, raw_distance) for cloth, raw_distance in rows]


def find_similar_by_image(
    db: Session,
    image_bytes: bytes,
    *,
    limit: int = 24,
    garment_type: GarmentZone | None = None,
    reference_type: TryOnReferenceType | None = None,
) -> list[SimilarCatalogItem]:
    """Embed a validated reference image and return similar catalog garments."""
    embedding = fashion_clip.encode_image_bytes(image_bytes)
    return _find_similar(
        db,
        embedding,
        limit=limit,
        garment_type=garment_type,
        reference_type=reference_type,
    )


def find_similar_by_catalog_item(
    db: Session,
    item: Cloth,
    *,
    limit: int = 12,
) -> list[SimilarCatalogItem]:
    """Use a catalog item's stored embedding, falling back to its source image."""
    reference_type = reference_type_for_cloth(item)
    if reference_type is None:
        raise ValueError("這件商品目前不支援試穿相似搜尋")
    embedding = item.embedding
    if embedding is None:
        try:
            image_bytes = Path(item.image_path).read_bytes()
        except OSError as error:
            raise ValueError("商品原圖目前無法讀取") from error
        embedding = fashion_clip.encode_image_bytes(image_bytes)
    return _find_similar(
        db,
        embedding,
        limit=limit,
        reference_type=reference_type,
        exclude_id=item.id,
    )
