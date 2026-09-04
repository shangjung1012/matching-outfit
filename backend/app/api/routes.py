from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.cloth import Cloth
from app.models.user_preference import UserPreference
from app.schemas import (
    CatalogItem,
    CatalogResponse,
    PlanRequest,
    PlanResponse,
    PreferenceConfirmation,
    PreferenceConfirmationResponse,
    PreferenceProposal,
    PreferenceProposalRequest,
    RecommendationResponse,
    RefineRequest,
    SearchRequest,
    SearchResponse,
    UserPreferenceUpdate,
    UserPreferenceView,
)
from app.services.catalog_search import search_catalog
from app.services.outfit_ranker import rank_outfits
from app.services.query_planner import query_planner

router = APIRouter()


@router.get("/health")
def api_health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/catalog", response_model=CatalogResponse)
def list_catalog(
    zone: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CatalogResponse:
    filters = []
    if zone:
        filters.append(Cloth.garment_zone == zone)
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Cloth.product_display_name.ilike(term),
                Cloth.article_type.ilike(term),
                Cloth.base_colour.ilike(term),
            )
        )
    total = db.scalar(select(func.count()).select_from(Cloth).where(*filters)) or 0
    clothes = db.scalars(select(Cloth).where(*filters).order_by(Cloth.id).offset(offset).limit(limit))
    return CatalogResponse(
        total=total,
        items=[
            CatalogItem(
                id=cloth.id,
                source_item_id=cloth.source_item_id,
                product_display_name=cloth.product_display_name,
                garment_zone=cloth.garment_zone,
                image_url=cloth.image_url,
                price=cloth.price,
                gender=cloth.gender,
                master_category=cloth.master_category,
                sub_category=cloth.sub_category,
                article_type=cloth.article_type,
                base_colour=cloth.base_colour,
                season=cloth.season,
                year=cloth.year,
                usage=cloth.usage,
                has_embedding=cloth.embedding is not None,
            )
            for cloth in clothes
        ],
    )


def preference_for(db: Session, user_key: str) -> UserPreference | None:
    return db.scalar(select(UserPreference).where(UserPreference.user_key == user_key))


@router.post("/query-plans", response_model=PlanResponse)
def create_query_plan(payload: PlanRequest, db: Session = Depends(get_db)) -> PlanResponse:
    return query_planner.plan(payload.user_input, preference_for(db, payload.user_key))


@router.post("/query-plans/refine", response_model=PlanResponse)
def refine_query_plan(payload: RefineRequest, db: Session = Depends(get_db)) -> PlanResponse:
    selected = [query for query in payload.existing_queries if query.selected]
    original = " ".join(query.text for query in selected)
    return query_planner.plan(
        original or payload.user_input,
        preference_for(db, payload.user_key),
        payload.user_input,
        zones=[query.garment_zone for query in selected] or None,
    )


@router.post("/catalog/search", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    try:
        results = search_catalog(db, payload.queries, payload.top_k)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Embedding search unavailable: {error}") from error
    return SearchResponse(results=results, model=settings.fashion_clip_model)


@router.post("/recommendations", response_model=RecommendationResponse)
def recommendations(payload: SearchRequest, db: Session = Depends(get_db)) -> RecommendationResponse:
    try:
        groups = search_catalog(db, payload.queries, payload.top_k)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Embedding search unavailable: {error}") from error
    return RecommendationResponse(recommendations=rank_outfits(groups))


@router.post("/preferences/proposals", response_model=PreferenceProposal)
def propose_preference_update(
    payload: PreferenceProposalRequest, db: Session = Depends(get_db)
) -> PreferenceProposal:
    clothes = db.scalars(select(Cloth).where(Cloth.id.in_(payload.liked_item_ids))).all()
    if not clothes:
        raise HTTPException(status_code=404, detail="No matching clothes found")
    colors = [cloth.base_colour for cloth in clothes if cloth.base_colour]
    article_types = [cloth.article_type for cloth in clothes if cloth.article_type]
    return PreferenceProposal(
        favorite_colors_to_add=[value for value, _ in Counter(colors).most_common(3)],
        favorite_article_types_to_add=[value for value, _ in Counter(article_types).most_common(3)],
        explanation="This is only a proposal. Persist it after the user explicitly confirms.",
    )


@router.post("/preferences/confirm", response_model=PreferenceConfirmationResponse)
def confirm_preference_update(
    payload: PreferenceConfirmation, db: Session = Depends(get_db)
) -> PreferenceConfirmationResponse:
    preference = preference_for(db, payload.user_key)
    if preference is None:
        preference = UserPreference(user_key=payload.user_key)
        db.add(preference)
    preference.favorite_colors = list(
        dict.fromkeys([*(preference.favorite_colors or []), *payload.favorite_colors_to_add])
    )
    preference.favorite_article_types = list(
        dict.fromkeys(
            [*(preference.favorite_article_types or []), *payload.favorite_article_types_to_add]
        )
    )
    db.commit()
    return PreferenceConfirmationResponse(status="updated", user_key=payload.user_key)


@router.get("/preferences/{user_key}", response_model=UserPreferenceView)
def get_user_preference(user_key: str, db: Session = Depends(get_db)) -> UserPreferenceView:
    preference = preference_for(db, user_key)
    if preference is None:
        return UserPreferenceView(user_key=user_key)
    return UserPreferenceView(
        user_key=preference.user_key,
        favorite_colors=preference.favorite_colors or [],
        disliked_colors=preference.disliked_colors or [],
        preferred_price_min=preference.preferred_price_min,
        preferred_price_max=preference.preferred_price_max,
        preferred_styles=preference.preferred_styles or [],
        preferred_categories=preference.preferred_categories or [],
        preferred_usages=preference.preferred_usages or [],
        favorite_article_types=preference.favorite_article_types or [],
        disliked_article_types=preference.disliked_article_types or [],
        notes=preference.notes,
    )


@router.put("/preferences/{user_key}", response_model=UserPreferenceView)
def update_user_preference(
    user_key: str, payload: UserPreferenceUpdate, db: Session = Depends(get_db)
) -> UserPreferenceView:
    if payload.user_key != user_key:
        raise HTTPException(status_code=400, detail="user_key in path and body must match")
    preference = preference_for(db, user_key)
    if preference is None:
        preference = UserPreference(user_key=user_key)
        db.add(preference)
    for field in (
        "favorite_colors",
        "disliked_colors",
        "preferred_price_min",
        "preferred_price_max",
        "preferred_styles",
        "preferred_categories",
        "preferred_usages",
        "favorite_article_types",
        "disliked_article_types",
        "notes",
    ):
        setattr(preference, field, getattr(payload, field))
    db.commit()
    db.refresh(preference)
    return get_user_preference(user_key, db)
