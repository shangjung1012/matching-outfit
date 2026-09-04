from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cloth import Cloth
from app.schemas import ClothResult, QueryDraft, QuerySearchResult
from app.services.fashion_clip import fashion_clip


def search_catalog(db: Session, queries: list[QueryDraft], top_k: int) -> list[QuerySearchResult]:
    selected = [query for query in queries if query.selected]
    if not selected:
        return []
    vectors = fashion_clip.encode_texts([query.text for query in selected])
    output: list[QuerySearchResult] = []
    for query, vector in zip(selected, vectors, strict=True):
        distance = Cloth.embedding.cosine_distance(vector).label("distance")
        statement = (
            select(Cloth, distance)
            .where(Cloth.embedding.is_not(None), Cloth.garment_zone == query.garment_zone)
            .order_by(distance)
            .limit(top_k)
        )
        clothes = [
            ClothResult(
                id=cloth.id,
                source_item_id=cloth.source_item_id,
                product_display_name=cloth.product_display_name,
                garment_zone=cloth.garment_zone,
                image_url=cloth.image_url,
                price=cloth.price,
                base_colour=cloth.base_colour,
                article_type=cloth.article_type,
                similarity=round(1.0 - float(value), 4),
            )
            for cloth, value in db.execute(statement).all()
        ]
        output.append(QuerySearchResult(query=query, clothes=clothes))
    return output
