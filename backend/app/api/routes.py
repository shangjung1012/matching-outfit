from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.cloth import Cloth
from app.models.fashion_knowledge import FashionArticle, FashionObservation
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
    FashionKnowledgeStatus,
    StylingDemoRequest,
    StylingDemoResponse,
    StylingCatalogRequest,
    StylingCatalogResponse,
)
from app.services.catalog_search import search_catalog
from app.services.outfit_ranker import rank_outfits
from app.services.query_planner import query_planner
from app.services.fashion_knowledge import FashionKnowledgeStore, retrieve_observations
from app.services.fashion_knowledge_repository import infer_audience, retrieve_observations_from_db
from app.services.knowledge_query_planner import KnowledgeQueryPlanner
from app.services.structured_llm import StructuredLLM
from app.services.text_embeddings import TextEmbeddingService
from app.services.styling_agent import StylingAgent
from app.services.formula_catalog_search import search_formula_catalog
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


@router.post("/styling/demo", response_model=StylingDemoResponse)
def styling_demo(
    payload: StylingDemoRequest, db: Session = Depends(get_db)
) -> StylingDemoResponse:
    store = fashion_knowledge_store()
    try:
        embedder = TextEmbeddingService(
            settings.openai_api_key,
            settings.knowledge_embedding_model,
            settings.knowledge_embedding_dimensions,
        )
        observations = retrieve_observations_from_db(
            db,
            payload.user_input,
            payload.top_k_observations,
            embedder,
            audience=payload.audience,
        )
        if not observations:
            observations = retrieve_observations(
                payload.user_input, store.observations(), payload.top_k_observations
            )
        agent = StylingAgent(
            StructuredLLM(settings.openai_api_key), settings.styling_planner_model
        )
        return agent.run(payload.user_input, observations, revise_once=payload.revise_once)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def preference_context(preference: UserPreference | None) -> dict:
    if preference is None:
        return {}
    return {
        "favorite_colors": preference.favorite_colors or [],
        "disliked_colors": preference.disliked_colors or [],
        "preferred_price_min": preference.preferred_price_min,
        "preferred_price_max": preference.preferred_price_max,
        "preferred_styles": preference.preferred_styles or [],
        "preferred_categories": preference.preferred_categories or [],
        "preferred_usages": preference.preferred_usages or [],
        "favorite_article_types": preference.favorite_article_types or [],
        "disliked_article_types": preference.disliked_article_types or [],
        "notes": preference.notes,
    }


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


@router.post("/styling/recommendations", response_model=StylingCatalogResponse)
def styling_catalog_recommendations(
    payload: StylingCatalogRequest, db: Session = Depends(get_db)
) -> StylingCatalogResponse:
    embedded_count = db.scalar(
        select(func.count()).select_from(Cloth).where(Cloth.embedding.is_not(None))
    )
    if not embedded_count:
        raise HTTPException(
            status_code=409,
            detail="No catalog embeddings are available. Import clothes and build embeddings first.",
        )
    preference = preference_for(db, payload.user_key)
    store = fashion_knowledge_store()
    try:
        embedder = TextEmbeddingService(
            settings.openai_api_key,
            settings.knowledge_embedding_model,
            settings.knowledge_embedding_dimensions,
        )
        observations = retrieve_observations_from_db(
            db,
            payload.user_input,
            payload.top_k_observations,
            embedder,
            audience=payload.audience,
        )
        if not observations:
            observations = retrieve_observations(
                payload.user_input, store.observations(), payload.top_k_observations
            )
        agent = StylingAgent(
            StructuredLLM(settings.openai_api_key), settings.styling_planner_model
        )
        styling = agent.run(
            payload.user_input,
            observations,
            revise_once=payload.revise_once,
            preference_context=preference_context(preference),
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    try:
        matches = [
            search_formula_catalog(
                db,
                formula,
                candidates_per_zone=payload.candidates_per_zone,
                outfits_per_formula=payload.outfits_per_formula,
                preference=preference,
                audience=infer_audience(payload.user_input, payload.audience),
            )
            for formula in styling.final_draft.outfits
        ]
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"FashionCLIP search unavailable: {error}") from error
    return StylingCatalogResponse(
        styling=styling,
        matches=matches,
        embedding_model=settings.fashion_clip_model,
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


def preference_for(db: Session, user_key: str) -> UserPreference | None:
    return db.scalar(select(UserPreference).where(UserPreference.user_key == user_key))


@router.post("/query-plans", response_model=PlanResponse)
def create_query_plan(payload: PlanRequest, db: Session = Depends(get_db)) -> PlanResponse:
    preference = preference_for(db, payload.user_key)
    audience = infer_audience(payload.user_input, payload.audience)
    try:
        observations = semantic_fashion_knowledge(
            db, payload.user_input, audience=audience, top_k=8
        )
        planner = KnowledgeQueryPlanner(
            StructuredLLM(settings.openai_api_key), settings.styling_planner_model
        )
        return planner.plan(
            payload.user_input,
            observations,
            audience=audience,
            preference=preference,
        )
    except RuntimeError as error:
        fallback = query_planner.plan(payload.user_input, preference)
        fallback.audience = audience
        fallback.planning_note = f"Knowledge agent unavailable; rule-based fallback used: {error}"
        return fallback


@router.post("/query-plans/refine", response_model=PlanResponse)
def refine_query_plan(payload: RefineRequest, db: Session = Depends(get_db)) -> PlanResponse:
    selected = [query for query in payload.existing_queries if query.selected]
    original = payload.original_input.strip() or " ".join(query.text for query in selected)
    combined = f"{original} {payload.user_input}".strip()
    preference = preference_for(db, payload.user_key)
    audience = infer_audience(combined, payload.audience)
    try:
        observations = semantic_fashion_knowledge(
            db, combined, audience=audience, top_k=8
        )
        planner = KnowledgeQueryPlanner(
            StructuredLLM(settings.openai_api_key), settings.styling_planner_model
        )
        return planner.plan(
            original or payload.user_input,
            observations,
            audience=audience,
            preference=preference,
            existing_queries=selected,
            refinement=payload.user_input,
        )
    except RuntimeError as error:
        fallback = query_planner.plan(
            original or payload.user_input,
            preference,
            payload.user_input,
            zones=[query.garment_zone for query in selected] or None,
        )
        fallback.audience = audience
        fallback.planning_note = f"Knowledge agent unavailable; rule-based fallback used: {error}"
        return fallback


@router.post("/catalog/search", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    try:
        audience = infer_audience(payload.user_input, payload.audience)
        results = search_catalog(db, payload.queries, payload.top_k, audience=audience)
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
    try:
        groups = search_catalog(
            db, payload.queries, payload.top_k, audience=audience
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Embedding search unavailable: {error}") from error
    ranked_pool = rank_outfits(
        groups,
        limit=min(750, max(200, payload.shortlist_count * 20)),
        preference=preference_for(db, payload.user_key),
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
        reviewer = AestheticReviewer(
            StructuredLLM(settings.openai_api_key), settings.aesthetic_review_model
        )
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
