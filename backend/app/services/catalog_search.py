from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.cloth import Cloth
from app.models.user_preference import UserHardRule
from app.schemas import (
    ClothResult, QueryDraft, QuerySearchResult, ReferenceLink, RequirementSummary, ShoeSpec,
)
from app.services.integration_tools.fashion_clip import fashion_clip
from app.services.query_planner import is_skirt_outfit_request


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
    """Hard exclusion gates applied to every catalog search."""
    conditions = []
    if hard.avoid_colours:
        conditions.append(_not_in_ci(Cloth.base_colour, hard.avoid_colours))
    if hard.avoid_article_types:
        conditions.append(_not_in_ci(Cloth.article_type, hard.avoid_article_types))
    if hard.avoid_master_categories:
        conditions.append(_not_in_ci(Cloth.master_category, hard.avoid_master_categories))
    return conditions


def _rows_to_results(
    db: Session, statement: Select, references: list[ReferenceLink] | None = None
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
            references=references or [],
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
    user_input: str = "",
    requirements: RequirementSummary | None = None,
) -> list[QuerySearchResult]:
    # only search queries that are selected
    selected = [query for query in queries if query.selected]
    if not selected:
        return []

    # hard preference:
    # price_min/max => keep_filters
    # avoid_{colours, article_types, master_categories} => exclusion filters
    keep_filters = _price_filters(hard) if hard is not None else []
    drop_filters = _exclusion_filters(hard) if hard is not None else []

    # encode the queries(default = 6) into FashionCLIP vectors
    vectors = fashion_clip.encode_texts([query.text for query in selected])
    output: list[QuerySearchResult] = []
    skirt_outfit_only = is_skirt_outfit_request(user_input, requirements)

    # search the catalog for each query
    for query, vector in zip(selected, vectors, strict=True):
        distance = Cloth.embedding.cosine_distance(vector).label("distance")
        base = [Cloth.embedding.is_not(None), Cloth.garment_zone == query.garment_zone]
        if skirt_outfit_only and query.garment_zone == "lower_body":
            base.append(func.lower(Cloth.article_type).in_(["skirt", "skirts"]))
        elif skirt_outfit_only and query.garment_zone == "one_piece":
            base.append(func.lower(Cloth.article_type).in_(["dress", "dresses"]))
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

        clothes = _rows_to_results(db, statement_for(drop_filters), query.references)
        output.append(QuerySearchResult(query=query, clothes=clothes, relaxed=False))
    return output


def search_catalog_items(
    db: Session,
    text: str,
    top_k: int,
    *,
    zone: str | None = None,
    audience: str | None = None,
    hard: UserHardRule | None = None,
) -> list[ClothResult]:
    """Search catalog image embeddings with one free-text FashionCLIP query."""
    vector = fashion_clip.encode_texts([text])[0]
    distance = Cloth.embedding.cosine_distance(vector).label("distance")
    base = [Cloth.embedding.is_not(None)]
    if zone:
        base.append(Cloth.garment_zone == zone)
    if audience == "men":
        base.append(Cloth.gender.in_(["Men", "Unisex"]))
    elif audience == "women":
        base.append(Cloth.gender.in_(["Women", "Unisex"]))

    keep_filters = _price_filters(hard) if hard is not None else []
    drop_filters = _exclusion_filters(hard) if hard is not None else []

    def statement_for(extra: list) -> Select:
        return (
            select(Cloth, distance)
            .where(*base, *keep_filters, *extra)
            .order_by(distance)
            .limit(top_k)
        )

    return _rows_to_results(db, statement_for(drop_filters))


def search_shoe_candidates(
    db: Session,
    specs: list[ShoeSpec],
    *,
    audience: str | None = None,
    hard: UserHardRule | None = None,
    top_k: int = 5,
) -> list[list[ClothResult]]:
    """Return strict `sub_category=Shoes` candidates for each shoe brief."""
    if not specs:
        return []
    vectors = fashion_clip.encode_texts([spec.shoe_query for spec in specs])
    keep_filters = _price_filters(hard) if hard is not None else []
    drop_filters = _exclusion_filters(hard) if hard is not None else []
    matches: list[list[ClothResult]] = []
    for vector in vectors:
        distance = Cloth.embedding.cosine_distance(vector).label("distance")
        filters = [
            Cloth.embedding.is_not(None),
            func.lower(Cloth.sub_category) == "shoes",
            *keep_filters,
            *drop_filters,
        ]
        if audience == "men":
            filters.append(Cloth.gender.in_(["Men", "Unisex"]))
        elif audience == "women":
            filters.append(Cloth.gender.in_(["Women", "Unisex"]))
        rows = _rows_to_results(
            db, select(Cloth, distance).where(*filters).order_by(distance).limit(top_k)
        )
        matches.append(rows)
    return matches


def search_best_shoes(
    db: Session,
    specs: list[ShoeSpec],
    *,
    audience: str | None = None,
    hard: UserHardRule | None = None,
) -> list[ClothResult | None]:
    """Compatibility wrapper returning the best strict-shoe result per brief."""
    return [
        candidates[0] if candidates else None
        for candidates in search_shoe_candidates(db, specs, audience=audience, hard=hard, top_k=1)
    ]
