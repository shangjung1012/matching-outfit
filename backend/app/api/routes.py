from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.cloth import Cloth
from app.models.fashion_knowledge import FashionArticle, FashionObservation
from app.models.user_preference import UserHardRule, UserStylePreference
from app.preferences.context import (
    build_planner_preference_context,
    outfit_context_embedding_text,
)
from app.schemas import (
    CatalogItem,
    CatalogResponse,
    CatalogSemanticSearchRequest,
    CatalogSemanticSearchResponse,
    ClarificationRequest,
    ClarificationResponse,
    HardRulesUpdate,
    HardRulesView,
    PlanRequest,
    PlanResponse,
    PreferenceBundle,
    RecommendationResponse,
    RefineRequest,
    SearchRequest,
    SearchResponse,
    StylePreferenceConfirmRequest,
    StylePreferenceCreate,
    StylePreferenceMutationResponse,
    StylePreferencePatch,
    StylePreferenceProposal,
    StylePreferenceProposalRequest,
    StylePreferenceView,
    FashionKnowledgeStatus,
)
from app.services.catalog_search import search_catalog, search_catalog_items
from app.services.outfit_ranker import rank_outfits
from app.knowledge.store import FashionKnowledgeStore
from app.knowledge.retrieval import infer_audience, retrieve_observations_from_db
from app.services.query_planner import QueryPlanner, RequirementCollector
from app.services.integration_tools.llm import LLM
from app.services.integration_tools.text_embeddings import TextEmbeddingService
from app.services.aesthetic_reviewer import AestheticReviewer, apply_aesthetic_reviews
from app.services.outfit_ranker import select_diverse

router = APIRouter()


def fashion_knowledge_store() -> FashionKnowledgeStore:
    return FashionKnowledgeStore(settings.article_data_dir)


@router.get("/health")
def api_health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/fashion-knowledge/status", response_model=FashionKnowledgeStatus)
def fashion_knowledge_status(db: Session = Depends(get_db)) -> FashionKnowledgeStatus:
    store = fashion_knowledge_store()
    audience_counts: Counter[str] = Counter()
    for audiences in db.scalars(select(FashionObservation.audiences)):
        audience_counts.update(audiences or [])
    return FashionKnowledgeStatus(
        article_count=db.scalar(select(func.count()).select_from(FashionArticle)) or 0,
        observation_count=db.scalar(select(func.count()).select_from(FashionObservation)) or 0,
        embedded_observation_count=db.scalar(
            select(func.count())
            .select_from(FashionObservation)
            .where(FashionObservation.embedding.is_not(None))
        )
        or 0,
        audience_counts=dict(audience_counts),
        data_dir=str(store.data_dir),
    )


HARD_RULE_SCALAR_FIELDS = (
    "gender",
    "age",
    "height_cm",
    "weight_kg",
    "price_min",
    "price_max",
    "notes",
)
HARD_RULE_LIST_FIELDS = (
    "avoid_colours",
    "avoid_article_types",
    "avoid_master_categories",
)
HARD_RULE_FIELDS = (*HARD_RULE_SCALAR_FIELDS, *HARD_RULE_LIST_FIELDS)


def hard_rules_payload(preference: UserHardRule | None) -> dict:
    if preference is None:
        return {
            **{field: None for field in HARD_RULE_SCALAR_FIELDS},
            **{field: [] for field in HARD_RULE_LIST_FIELDS},
        }
    return {field: getattr(preference, field) for field in HARD_RULE_FIELDS}


def effective_audience(
    query: str, explicit: str | None, profile: UserHardRule | None
) -> str | None:
    requested = infer_audience(query, explicit)
    if requested:
        return requested
    if profile is not None and profile.gender == "female":
        return "women"
    if profile is not None and profile.gender == "male":
        return "men"
    return None


def semantic_fashion_knowledge(
    db: Session,
    user_input: str,
    *,
    audience: str | None = None,
    top_k: int = 8,
):
    embedder = TextEmbeddingService(
        settings.openai_api_key,
        settings.knowledge_embedding_model,
        settings.knowledge_embedding_dimensions,
    )
    return retrieve_observations_from_db(
        db, user_input, top_k, embedder, audience=audience
    )


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
            )
            for cloth in clothes
        ],
    )


@router.post("/catalog/semantic-search", response_model=CatalogSemanticSearchResponse)
def semantic_catalog_search(
    payload: CatalogSemanticSearchRequest, db: Session = Depends(get_db)
) -> CatalogSemanticSearchResponse:
    hard = hard_rules_for(db, payload.user_key)
    audience = effective_audience(payload.query, payload.audience, hard)
    try:
        items = search_catalog_items(
            db,
            payload.query,
            payload.limit,
            zone=payload.zone,
            audience=audience,
            hard=hard,
        )
    except Exception as error:
        raise HTTPException(
            status_code=503, detail=f"Embedding search unavailable: {error}"
        ) from error
    return CatalogSemanticSearchResponse(
        query=payload.query,
        items=items,
        total=len(items),
        model=settings.fashion_clip_model,
    )


def hard_rules_for(db: Session, user_key: str) -> UserHardRule | None:
    return db.scalar(select(UserHardRule).where(UserHardRule.user_key == user_key))


def style_preferences_for(
    db: Session, user_key: str, *, only_active: bool = True
) -> list[UserStylePreference]:
    statement = select(UserStylePreference).where(UserStylePreference.user_key == user_key)
    if only_active:
        statement = statement.where(UserStylePreference.is_active.is_(True))
    return list(db.scalars(statement.order_by(UserStylePreference.id)))


def upsert_style_preference(
    db: Session,
    user_key: str,
    row: StylePreferenceCreate,
    *,
    confirmed: bool = False,
) -> tuple[UserStylePreference, bool]:
    """Insert a preference sentence or merge an exact duplicate."""
    existing = db.scalar(
        select(UserStylePreference).where(
            UserStylePreference.user_key == user_key,
            UserStylePreference.preference_text == row.preference_text,
        )
    )
    now = datetime.now(timezone.utc)
    if existing is None:
        created = UserStylePreference(
            user_key=user_key,
            preference_text=row.preference_text,
            source=row.source,
            origin_item_ids=row.origin_item_ids,
            occasions=row.occasions,
            seasons=row.seasons,
            times_of_day=row.times_of_day,
            climates=row.climates,
            formalities=row.formalities,
            activities=row.activities,
            styles=row.styles,
            is_active=True,
            confirmed_at=now if confirmed else None,
        )
        db.add(created)
        return created, True

    existing.is_active = True
    for field in (
        "occasions", "seasons", "times_of_day", "climates",
        "formalities", "activities", "styles",
    ):
        setattr(existing, field, sorted({*getattr(existing, field), *getattr(row, field)}))
    existing.origin_item_ids = sorted({*existing.origin_item_ids, *row.origin_item_ids})
    if confirmed:
        existing.confirmed_at = now
    return existing, False


def outfit_memory_proposals(
    clothes_by_id: dict[int, Cloth], payload: StylePreferenceProposalRequest
) -> list[StylePreferenceCreate]:
    proposals: list[StylePreferenceCreate] = []
    seen_outfits: set[tuple[int, ...]] = set()
    for item_ids in payload.outfit_item_ids:
        identity = tuple(dict.fromkeys(item_ids))
        if not identity or identity in seen_outfits:
            continue
        seen_outfits.add(identity)
        clothes = [clothes_by_id[item_id] for item_id in identity if item_id in clothes_by_id]
        if not clothes:
            continue
        outfit_description = "、".join(cloth.product_display_name for cloth in clothes)
        sentence = (
            f"在「{payload.user_request.strip()}」的需求下，"
            f"使用者喜歡由 {outfit_description} 組成的整套搭配。"
        )
        if len(sentence) > 500:
            sentence = f"{sentence[:497]}..."
        proposals.append(
            StylePreferenceCreate(
                preference_text=sentence,
                source="implicit",
                origin_item_ids=[str(cloth.id) for cloth in clothes],
                occasions=payload.requirements.occasions if payload.requirements else [],
                seasons=payload.requirements.seasons if payload.requirements else [],
                times_of_day=payload.requirements.times_of_day if payload.requirements else [],
                climates=payload.requirements.climates if payload.requirements else [],
                formalities=payload.requirements.formalities if payload.requirements else [],
                activities=payload.requirements.activities if payload.requirements else [],
                styles=payload.requirements.styles if payload.requirements else [],
            )
        )
    return proposals


@router.post("/query-plans", response_model=PlanResponse)
def create_query_plan(payload: PlanRequest, db: Session = Depends(get_db)) -> PlanResponse:
    preference = hard_rules_for(db, payload.user_key)
    style_preferences = style_preferences_for(db, payload.user_key)
    audience = effective_audience(payload.user_input, payload.audience, preference)
    try:
        planner = QueryPlanner(LLM())
        return planner.plan(
            payload.user_input,
            audience=audience,
            hard=preference,
            style_preferences=style_preferences,
            requirements=payload.requirements,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=f"Query planner unavailable: {error}") from error


@router.post("/query-plans/clarify", response_model=ClarificationResponse)
def clarify_requirements(
    payload: ClarificationRequest, db: Session = Depends(get_db)
) -> ClarificationResponse:
    user_text = " ".join(
        message.text for message in payload.messages if message.role == "user"
    )
    preference = hard_rules_for(db, payload.user_key)
    audience = effective_audience(user_text, payload.audience, preference)
    try:
        return RequirementCollector(LLM()).collect(
            payload.messages,
            audience=audience,
            previous_requirements=payload.previous_requirements,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=503, detail=f"Requirement agent unavailable: {error}"
        ) from error


@router.post("/query-plans/refine", response_model=PlanResponse)
def refine_query_plan(payload: RefineRequest, db: Session = Depends(get_db)) -> PlanResponse:
    selected = [query for query in payload.existing_queries if query.selected]
    original = payload.original_input.strip() or " ".join(query.text for query in selected)
    combined = f"{original} {payload.user_input}".strip()
    preference = hard_rules_for(db, payload.user_key)
    style_preferences = style_preferences_for(db, payload.user_key)
    audience = effective_audience(combined, payload.audience, preference)
    try:
        planner = QueryPlanner(LLM())
        return planner.plan(
            original or payload.user_input,
            audience=audience,
            hard=preference,
            style_preferences=style_preferences,
            requirements=payload.requirements,
            existing_queries=selected,
            refinement=payload.user_input,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=f"Query planner unavailable: {error}") from error


@router.post("/catalog/search", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    try:
        hard = hard_rules_for(db, payload.user_key)
        audience = effective_audience(payload.user_input, payload.audience, hard)
        results = search_catalog(
            db,
            payload.queries,
            payload.top_k,
            audience=audience,
            hard=hard,
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Embedding search unavailable: {error}") from error
    return SearchResponse(results=results, model=settings.fashion_clip_model)


@router.post("/recommendations", response_model=RecommendationResponse)
def recommendations(payload: SearchRequest, db: Session = Depends(get_db)) -> RecommendationResponse:
    hard = hard_rules_for(db, payload.user_key)
    audience = effective_audience(payload.user_input, payload.audience, hard)
    try:
        groups = search_catalog(
            db, payload.queries, payload.top_k, audience=audience, hard=hard
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Embedding search unavailable: {error}") from error
    ranked_pool = rank_outfits(
        groups,
        limit=min(750, max(200, payload.shortlist_count * 20)),
        user_context=payload.user_input,
    )
    shortlist = select_diverse(ranked_pool, payload.shortlist_count)
    if not shortlist:
        return RecommendationResponse(
            recommendations=[],
            review_note="No valid outfit combinations",
        )

    should_review = (
        payload.use_aesthetic_review
        and settings.aesthetic_review_enabled
        and bool(settings.openai_api_key)
    )
    if not should_review:
        note = (
            "Aesthetic review skipped because OPENAI_API_KEY is not configured"
            if payload.use_aesthetic_review and not settings.openai_api_key
            else "Aesthetic review disabled"
        )
        return RecommendationResponse(
            recommendations=select_diverse(shortlist, payload.final_count),
            aesthetic_reviewed=False,
            review_note=note,
        )

    knowledge_query = outfit_context_embedding_text(
        payload.requirements, payload.user_input
    )[:4000]
    observations = []
    knowledge_note = ""
    try:
        observations = semantic_fashion_knowledge(
            db, knowledge_query, audience=audience, top_k=12
        )
    except RuntimeError as error:
        knowledge_note = f"Fashion knowledge retrieval unavailable: {error}"

    style_preferences = style_preferences_for(db, payload.user_key)
    preference_context = build_planner_preference_context(hard, style_preferences)
    try:
        reviewer = AestheticReviewer(LLM())
        reviews = reviewer.review(
            payload.user_input,
            shortlist,
            observations=observations,
            user_preferences=preference_context,
        )
        final = apply_aesthetic_reviews(
            shortlist,
            reviews,
            final_count=payload.final_count,
            observations=observations,
        )
        used_observation_ids = list(
            dict.fromkeys(
                identifier
                for recommendation in final
                if recommendation.aesthetic_review is not None
                for identifier in recommendation.aesthetic_review.knowledge_observation_ids
            )
        )
        knowledge_sources = list(
            dict.fromkeys(
                reference.title
                for recommendation in final
                for reference in recommendation.references
            )
        )
        return RecommendationResponse(
            recommendations=final,
            aesthetic_reviewed=True,
            review_note=f"Outfit agent reviewed {len(reviews)} shortlisted outfits",
            knowledge_observation_count=len(used_observation_ids),
            knowledge_sources=knowledge_sources,
            knowledge_note=knowledge_note,
        )
    except RuntimeError as error:
        return RecommendationResponse(
            recommendations=select_diverse(shortlist, payload.final_count),
            aesthetic_reviewed=False,
            review_note=f"Aesthetic review unavailable; match ranking used instead: {error}",
            knowledge_note=knowledge_note,
        )


def _hard_rules_view(user_key: str, preference: UserHardRule | None) -> HardRulesView:
    return HardRulesView(user_key=user_key, **hard_rules_payload(preference))


@router.get("/preferences/{user_key}", response_model=PreferenceBundle)
def get_preferences(user_key: str, db: Session = Depends(get_db)) -> PreferenceBundle:
    """Everything the settings page needs in one call: hard gates + every soft row."""
    return PreferenceBundle(
        hard=_hard_rules_view(user_key, hard_rules_for(db, user_key)),
        soft=[
            StylePreferenceView.model_validate(row)
            for row in style_preferences_for(db, user_key, only_active=False)
        ],
    )


@router.put("/preferences/{user_key}/hard", response_model=HardRulesView)
def replace_hard_rules(
    user_key: str, payload: HardRulesUpdate, db: Session = Depends(get_db)
) -> HardRulesView:
    """Full-replace the hard constraint gates (price / avoid lists / gender / size)."""
    if payload.user_key != user_key:
        raise HTTPException(status_code=400, detail="user_key in path and body must match")
    preference = hard_rules_for(db, user_key)
    if preference is None:
        preference = UserHardRule(user_key=user_key)
        db.add(preference)
    for field in HARD_RULE_FIELDS:
        setattr(preference, field, getattr(payload, field))
    db.commit()
    db.refresh(preference)
    return _hard_rules_view(user_key, preference)


@router.get("/preferences/{user_key}/soft", response_model=list[StylePreferenceView])
def list_style_preferences(
    user_key: str,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[StylePreferenceView]:
    return [
        StylePreferenceView.model_validate(row)
        for row in style_preferences_for(db, user_key, only_active=not include_inactive)
    ]


@router.post("/preferences/{user_key}/soft", response_model=StylePreferenceView, status_code=201)
def add_style_preference(
    user_key: str, payload: StylePreferenceCreate, db: Session = Depends(get_db)
) -> StylePreferenceView:
    """Add one user-authored (explicit) soft preference, or merge into its slot."""
    row, _ = upsert_style_preference(db, user_key, payload)
    db.commit()
    db.refresh(row)
    return StylePreferenceView.model_validate(row)


@router.patch(
    "/preferences/{user_key}/soft/{preference_id}", response_model=StylePreferenceView
)
def patch_style_preference(
    user_key: str,
    preference_id: int,
    payload: StylePreferencePatch,
    db: Session = Depends(get_db),
) -> StylePreferenceView:
    row = db.get(UserStylePreference, preference_id)
    if row is None or row.user_key != user_key:
        raise HTTPException(status_code=404, detail="Style preference not found")
    if payload.is_active is not None:
        row.is_active = payload.is_active
    if payload.preference_text is not None:
        row.preference_text = payload.preference_text
    db.commit()
    db.refresh(row)
    return StylePreferenceView.model_validate(row)


@router.delete("/preferences/{user_key}/soft/{preference_id}", status_code=204)
def delete_style_preference(
    user_key: str, preference_id: int, db: Session = Depends(get_db)
) -> None:
    row = db.get(UserStylePreference, preference_id)
    if row is None or row.user_key != user_key:
        raise HTTPException(status_code=404, detail="Style preference not found")
    db.delete(row)
    db.commit()


@router.post(
    "/preferences/{user_key}/soft/from-outfit", response_model=StylePreferenceProposal
)
def propose_style_preferences(
    user_key: str,
    payload: StylePreferenceProposalRequest,
    db: Session = Depends(get_db),
) -> StylePreferenceProposal:
    """Decompose a liked outfit into candidate soft rows. Nothing is persisted."""
    if payload.user_key != user_key:
        raise HTTPException(status_code=400, detail="user_key in path and body must match")
    requested_ids = {
        item_id for outfit in payload.outfit_item_ids for item_id in outfit
    }
    clothes = db.scalars(select(Cloth).where(Cloth.id.in_(requested_ids))).all()
    if not clothes:
        raise HTTPException(status_code=404, detail="No matching clothes found")
    proposals = outfit_memory_proposals(
        {cloth.id: cloth for cloth in clothes}, payload
    )
    return StylePreferenceProposal(
        proposals=proposals,
        explanation="每一筆都是完整需求與所選搭配組成的偏好句，確認後才會儲存。",
    )


@router.post(
    "/preferences/{user_key}/soft/confirm", response_model=StylePreferenceMutationResponse
)
def confirm_style_preferences(
    user_key: str,
    payload: StylePreferenceConfirmRequest,
    db: Session = Depends(get_db),
) -> StylePreferenceMutationResponse:
    """Persist confirmed rows as ``implicit`` soft preferences (upsert per slot)."""
    if payload.user_key != user_key:
        raise HTTPException(status_code=400, detail="user_key in path and body must match")
    created = updated = 0
    for row in payload.rows:
        _, was_created = upsert_style_preference(db, user_key, row, confirmed=True)
        created += int(was_created)
        updated += int(not was_created)
    db.commit()
    return StylePreferenceMutationResponse(
        status="ok", user_key=user_key, created=created, updated=updated
    )
