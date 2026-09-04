from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.cloth import Cloth
from app.models.user_preference import UserHardRule
from app.schemas import ClothResult, QueryDraft, QuerySearchResult
from app.services.integration_tools.fashion_clip import fashion_clip


def _price_filters(hard: UserHardRule) -> list:
    """Structural gates - kept even when a zone has to be relaxed."""
    conditions = []
    if hard.price_min is not None:
        conditions.append(Cloth.price >= hard.price_min)
    if hard.price_max is not None:
        conditions.append(Cloth.price <= hard.price_max)
    return conditions


def _not_in_ci(column, values: list[str]) -> object:
    # NULL columns are not an exclusion match, so keep them.
    return or_(column.is_(None), func.lower(column).notin_([value.lower() for value in values]))


def _exclusion_filters(hard: UserHardRule) -> list:
    """"Avoid" gates - dropped for a single zone if they empty its candidate pool."""
    conditions = []
    if hard.avoid_colours:
        conditions.append(_not_in_ci(Cloth.base_colour, hard.avoid_colours))
    if hard.avoid_article_types:
        conditions.append(_not_in_ci(Cloth.article_type, hard.avoid_article_types))
    if hard.avoid_master_categories:
        conditions.append(_not_in_ci(Cloth.master_category, hard.avoid_master_categories))
    return conditions


def _rows_to_results(
    db: Session, statement: Select, source_urls: list[str] | None = None
) -> list[ClothResult]:
    return [
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
            source_urls=source_urls or [],
            image_path=cloth.image_path,
        )
        for cloth, value in db.execute(statement).all()
    ]

# use SQLAlchemy to search the catalog for each query, applying hard rules and returning results
def search_catalog(
    db: Session,
    queries: list[QueryDraft],
    top_k: int,
    audience: str | None = None,
    hard: UserHardRule | None = None,
) -> list[QuerySearchResult]:
    # only search queries that are selected
    selected = [query for query in queries if query.selected]
    if not selected:
        return []

    # hard preference:
    # price_min/max => keep_filters
    # avoid_{colours, article_types, master_categories} => drop_filters
    keep_filters = _price_filters(hard) if hard is not None else []
    drop_filters = _exclusion_filters(hard) if hard is not None else []

    # encode the queries(default = 6) into FashionCLIP vectors
    vectors = fashion_clip.encode_texts([query.text for query in selected])
    output: list[QuerySearchResult] = []

    # search the catalog for each query
    for query, vector in zip(selected, vectors, strict=True):
        distance = Cloth.embedding.cosine_distance(vector).label("distance")
        base = [Cloth.embedding.is_not(None), Cloth.garment_zone == query.garment_zone]
        if audience == "men":
            base.append(Cloth.gender.in_(["Men", "Unisex"]))
        elif audience == "women":
            base.append(Cloth.gender.in_(["Women", "Unisex"]))

        def statement_for(extra: list) -> Select:
            return (
                select(Cloth, distance)
                .where(*base, *keep_filters, *extra)
                .order_by(distance)
                .limit(top_k)
            )

        clothes = _rows_to_results(db, statement_for(drop_filters), query.source_urls)
        relaxed = False
        if not clothes and drop_filters:
            # The user's "avoid" gates emptied this zone - relax them here only,
            # price/gender/zone stay enforced. The caller can surface `relaxed`.
            clothes = _rows_to_results(db, statement_for([]), query.source_urls)
            relaxed = True
        output.append(QuerySearchResult(query=query, clothes=clothes, relaxed=relaxed))
    return output
