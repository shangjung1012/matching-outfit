"""Image-to-catalog clothes similarity search pipeline."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cloth import Cloth
from app.schemas.workflow import ClothResult, GarmentZone
from app.services.integration_tools.fashion_clip import fashion_clip


def find_similar_by_image(
    db: Session,
    image_bytes: bytes,
    *,
    limit: int = 24,
    garment_type: GarmentZone | None = None,
) -> list[ClothResult]:
    """Embed a validated reference image and return similar catalog garments."""
    # 1. Encode the uploaded reference image in the same FashionCLIP space as the catalog.
    embedding = fashion_clip.encode_image_bytes(image_bytes)

    # 2. Let pgvector rank embedded catalog garments by cosine distance (smallest first).
    distance = Cloth.embedding.cosine_distance(embedding).label("distance")
    conditions = [Cloth.embedding.is_not(None)]
    if garment_type is not None:
        conditions.append(Cloth.garment_zone == garment_type)
    statement = select(Cloth, distance).where(*conditions).order_by(distance).limit(limit)
    rows = db.execute(statement).all()

    # 3. Convert results into "ClothResult" objects with normalized similarity scores.
    results = []
    for cloth, raw_distance in rows:
        similarity = max(0.0, min(1.0, 1.0 - float(raw_distance)))
        results.append(
            ClothResult(
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
                gender=cloth.gender,
                base_colour=cloth.base_colour,
                article_type=cloth.article_type,
                similarity=round(similarity, 4),
            )
        )
    return results
