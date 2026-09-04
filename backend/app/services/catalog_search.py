from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cloth import Cloth
from app.schemas import ClothResult, QueryDraft, QuerySearchResult
from app.services.fashion_clip import fashion_clip


def search_catalog(
    db: Session,
    queries: list[QueryDraft],
    top_k: int,
    audience: str | None = None,
) -> list[QuerySearchResult]:
    selected = [query for query in queries if query.selected]
    if not selected:
        return []
    vectors = fashion_clip.encode_texts([query.text for query in selected])
    output: list[QuerySearchResult] = []
    for query, vector in zip(selected, vectors, strict=True):
        distance = Cloth.embedding.cosine_distance(vector).label("distance")
        filters = [Cloth.embedding.is_not(None), Cloth.garment_zone == query.garment_zone]
        if audience == "men":
            filters.append(Cloth.gender.in_(["Men", "Unisex"]))
        elif audience == "women":
            filters.append(Cloth.gender.in_(["Women", "Unisex"]))
        statement = select(Cloth, distance).where(*filters).order_by(distance).limit(top_k)
        clothes = [
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
                age_group=cloth.age_group,
                gender=cloth.gender,
                usage=cloth.usage,
                base_colour=cloth.base_colour,
                article_type=cloth.article_type,
                similarity=round(1.0 - float(value), 4),
                image_path=cloth.image_path,
            )
            for cloth, value in db.execute(statement).all()
        ]
        output.append(QuerySearchResult(query=query, clothes=clothes))
    return output
