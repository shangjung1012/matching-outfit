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
from app.schemas import (
    CatalogItem,
    CatalogResponse,
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
from app.services.catalog_search import search_catalog
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


HARD_RULE_SCALAR_FIELDS = ("price_min", "price_max", "notes")
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


def hard_rules_for(db: Session, user_key: str) -> UserHardRule | None:
    return db.scalar(select(UserHardRule).where(UserHardRule.user_key == user_key))


def style_preferences_for(
    db: Session, user_key: str, *, only_active: bool = True
) -> list[UserStylePreference]:
    statement = select(UserStylePreference).where(UserStylePreference.user_key == user_key)
    if only_active:
        statement = statement.where(UserStylePreference.is_active.is_(True))
    return list(db.scalars(statement.order_by(UserStylePreference.id)))


def _pref_zone(garment_zone: str | None) -> str:
    return garment_zone if garment_zone in {
        "upper_body",
        "lower_body",
        "one_piece",
        "accessory",
    } else "any"


def upsert_style_preference(
    db: Session,
    user_key: str,
    row: StylePreferenceCreate,
    *,
    confirmed: bool = False,
) -> tuple[UserStylePreference, bool]:
    """Insert a soft preference, or merge into the existing slot.

    The slot key mirrors the ``uq_user_style_preference_slot`` constraint
    (user_key, axis, value, zone, polarity). A repeated confirmation reactivates
    the row, nudges its weight up, and unions the context lists.
    """
    existing = db.scalar(
        select(UserStylePreference).where(
            UserStylePreference.user_key == user_key,
            UserStylePreference.axis == row.axis,
            UserStylePreference.value == row.value,
            UserStylePreference.zone == row.zone,
            UserStylePreference.polarity == row.polarity,
        )
    )
    now = datetime.now(timezone.utc)
    if existing is None:
        created = UserStylePreference(
            user_key=user_key,
            axis=row.axis,
            value=row.value,
            zone=row.zone,
            polarity=row.polarity,
            weight=row.weight,
            source=row.source,
            origin=row.origin,
            origin_item_ids=row.origin_item_ids,
            context_occasions=row.context_occasions,
            context_seasons=row.context_seasons,
            context_climates=row.context_climates,
            is_active=True,
            confirmed_at=now if confirmed else None,
        )
        db.add(created)
        return created, True

    existing.is_active = True
    existing.weight = min(1.0, max(existing.weight, row.weight) + (0.05 if confirmed else 0.0))
    existing.context_occasions = sorted({*existing.context_occasions, *row.context_occasions})
    existing.context_seasons = sorted({*existing.context_seasons, *row.context_seasons})
    existing.context_climates = sorted({*existing.context_climates, *row.context_climates})
    existing.origin_item_ids = sorted({*existing.origin_item_ids, *row.origin_item_ids})
    if confirmed:
        existing.confirmed_at = now
    return existing, False


def style_proposals_from_clothes(
    clothes: list[Cloth], payload: StylePreferenceProposalRequest
) -> list[StylePreferenceCreate]:
    context = {
        "context_occasions": payload.context_occasions,
        "context_seasons": payload.context_seasons,
        "context_climates": payload.context_climates,
    }
    origin_item_ids = [str(cloth.id) for cloth in clothes]
    colours: Counter[tuple[str, str]] = Counter()
    article_types: Counter[tuple[str, str]] = Counter()
    for cloth in clothes:
        zone = _pref_zone(cloth.garment_zone)
        if cloth.base_colour:
            colours[(zone, cloth.base_colour.strip().lower())] += 1
        if cloth.article_type:
            article_types[(zone, cloth.article_type.strip().lower())] += 1

    proposals: list[StylePreferenceCreate] = []
    for (zone, value), _ in colours.most_common(4):
        proposals.append(
            StylePreferenceCreate(
                axis="color",
                value=value,
                zone=zone,
                polarity="prefer",
                weight=0.2,
                source="implicit",
                origin="liked-outfit",
                origin_item_ids=origin_item_ids,
                **context,
            )
        )
    for (zone, value), _ in article_types.most_common(4):
        proposals.append(
            StylePreferenceCreate(
                axis="article_type",
                value=value,
                zone=zone,
                polarity="prefer",
                weight=0.2,
                source="implicit",
                origin="liked-outfit",
                origin_item_ids=origin_item_ids,
                **context,
            )
        )
    return proposals


@router.post("/query-plans", response_model=PlanResponse)
def create_query_plan(payload: PlanRequest, db: Session = Depends(get_db)) -> PlanResponse:
    preference = hard_rules_for(db, payload.user_key)
    style_preferences = style_preferences_for(db, payload.user_key)
    audience = infer_audience(payload.user_input, payload.audience)
    try:
        observations = semantic_fashion_knowledge(
            db, payload.user_input, audience=audience, top_k=8
        )
        planner = QueryPlanner(LLM())
        return planner.plan(
            payload.user_input,
            observations,
            audience=audience,
            hard=preference,
            style_preferences=style_preferences,
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
    audience = infer_audience(user_text, payload.audience)
    try:
        return RequirementCollector(LLM()).collect(
            payload.messages,
            audience=audience,
            hard=hard_rules_for(db, payload.user_key),
            style_preferences=style_preferences_for(db, payload.user_key),
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
    audience = infer_audience(combined, payload.audience)
    try:
        # 先嘗試把 user input + original 去找 fashion knowledge
        observations = semantic_fashion_knowledge(
            db, combined, audience=audience, top_k=8
        )
        planner = QueryPlanner(LLM())
        return planner.plan(
            original or payload.user_input,
            observations,
            audience=audience,
            hard=preference,
            style_preferences=style_preferences,
            existing_queries=selected,
            refinement=payload.user_input,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=f"Query planner unavailable: {error}") from error


@router.post("/catalog/search", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    try:
        audience = infer_audience(payload.user_input, payload.audience)
        results = search_catalog(
            db,
            payload.queries,
            payload.top_k,
            audience=audience,
            hard=hard_rules_for(db, payload.user_key),
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Embedding search unavailable: {error}") from error
    return SearchResponse(results=results, model=settings.fashion_clip_model)


@router.post("/recommendations", response_model=RecommendationResponse)
def recommendations(payload: SearchRequest, db: Session = Depends(get_db)) -> RecommendationResponse:
    audience = infer_audience(payload.user_input, payload.audience)
    observations = []
    knowledge_note = ""
    if payload.user_input:
        try:
            observations = semantic_fashion_knowledge(
                db, payload.user_input, audience=audience, top_k=8
            )
            knowledge_note = (
                f"Retrieved {len(observations)} semantic fashion observations"
            )
        except RuntimeError as error:
            knowledge_note = f"Fashion knowledge retrieval unavailable: {error}"
    knowledge_sources = list(
        dict.fromkeys(observation.source_title for observation in observations)
    )
    knowledge_fields = {
        "knowledge_observation_count": len(observations),
        "knowledge_sources": knowledge_sources,
        "knowledge_note": knowledge_note,
    }
    observation_context = " ".join(
        [
            observation.summary
            for observation in observations
            if observation.signal_type != "editorial_example"
        ]
    )
    ranking_context = f"{payload.user_input} {observation_context}".strip()
    hard = hard_rules_for(db, payload.user_key)
    style_preferences = style_preferences_for(db, payload.user_key)
    try:
        groups = search_catalog(
            db, payload.queries, payload.top_k, audience=audience, hard=hard
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Embedding search unavailable: {error}") from error
    ranked_pool = rank_outfits(
        groups,
        limit=min(750, max(200, payload.shortlist_count * 20)),
        style_preferences=style_preferences,
        user_context=payload.user_input,
    )
    shortlist = select_diverse(ranked_pool, payload.shortlist_count)
    if not shortlist:
        return RecommendationResponse(
            recommendations=[],
            review_note="No valid outfit combinations",
            **knowledge_fields,
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
            **knowledge_fields,
        )

    try:
        reviewer = AestheticReviewer(LLM())
        reviews = reviewer.review(ranking_context, shortlist)
        final = apply_aesthetic_reviews(shortlist, reviews, final_count=payload.final_count)
        return RecommendationResponse(
            recommendations=final,
            aesthetic_reviewed=True,
            review_note=f"Vision critic reviewed {len(reviews)} shortlisted outfits",
            **knowledge_fields,
        )
    except RuntimeError as error:
        return RecommendationResponse(
            recommendations=select_diverse(shortlist, payload.final_count),
            aesthetic_reviewed=False,
            review_note=f"Aesthetic review unavailable; match ranking used instead: {error}",
            **knowledge_fields,
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
    if payload.weight is not None:
        row.weight = payload.weight
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
    clothes = db.scalars(select(Cloth).where(Cloth.id.in_(payload.item_ids))).all()
    if not clothes:
        raise HTTPException(status_code=404, detail="No matching clothes found")
    return StylePreferenceProposal(proposals=style_proposals_from_clothes(list(clothes), payload))


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
