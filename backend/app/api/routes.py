from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.cloth import Cloth
from app.models.fashion_knowledge import FashionArticle, FashionObservation
from app.models.user_preference import UserHardRule, UserStylePreference
from app.models.user_favorite import (
    UserFavoriteItem,
    UserFavoriteOutfit,
    UserFavoriteOutfitItem,
)
from app.preferences.context import (
    build_planner_preference_context,
    outfit_context_embedding_text,
)
from app.schemas import (
    CatalogItem,
    CatalogResponse,
    CatalogSemanticSearchRequest,
    CatalogSemanticSearchResponse,
    FavoriteCollection,
    FavoriteItem,
    FavoriteOutfit,
    FavoriteOutfitUpdate,
    FavoriteItemsMutationResponse,
    FavoriteItemsUpdate,
    ClarificationRequest,
    ClarificationResponse,
    ClothResult,
    HardRulesUpdate,
    HardRulesView,
    PlanRequest,
    PlanResponse,
    PreferenceBundle,
    RecommendationResponse,
    RecommendationDebug,
    RefineRequest,
    SearchRequest,
    StylePreferenceAddRequest,
    SearchResponse,
    StylePreferenceConfirmRequest,
    StylePreferenceCreate,
    StylePreferenceMutationResponse,
    StylePreferencePatch,
    StylePreferenceProposal,
    StylePreferenceProposalRequest,
    StylePreferenceItemProposalRequest,
    StylePreferenceView,
    FashionKnowledgeStatus,
)
from app.schemas.workflow import GarmentZone, RequirementSummary
from app.services.catalog_search import search_catalog, search_catalog_items
from app.services.clothes_similarity import find_similar_by_image
from app.services.image_inputs.validation import validate_image
from app.services.outfit_ranker import rank_outfits
from app.services.post_review_shoes import attach_post_review_shoes
from app.services.outfit_compatibility import rerank_outfits_by_compatibility
from app.knowledge.store import FashionKnowledgeStore
from app.knowledge.retrieval import infer_audience, retrieve_observations_from_db
from app.services.query_planner import (
    FashionIntentInterpreter,
    QueryPlanner,
    RequirementCollector,
    interpret_fashion_intent_or_none,
)
from app.services.integration_tools.llm import LLM
from app.services.integration_tools.text_embeddings import TextEmbeddingService
from app.services.integration_tools.weather import with_weather_context
from app.services.aesthetic_reviewer import AestheticReviewer, apply_aesthetic_reviews
from app.services.outfit_ranker import select_diverse
from app.services.requirement_context import with_context_defaults

router = APIRouter()


@dataclass(frozen=True)
class RecommendationInput:
    payload: SearchRequest
    reference_content: bytes | None = None
    reference_type: Literal["upper_body", "lower_body"] | None = None


async def recommendation_input(request: Request) -> RecommendationInput:
    """Accept the legacy JSON request or an image-bearing multipart request."""
    try:
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            form = await request.form()
            raw_payload = form.get("payload")
            if not isinstance(raw_payload, str):
                raise HTTPException(status_code=422, detail="multipart request requires a JSON payload field")
            reference_image = form.get("reference_image")
            reference_type = form.get("reference_type")
            if reference_image is not None and not hasattr(reference_image, "read"):
                raise HTTPException(status_code=422, detail="reference_image 必須是圖片檔案")
            if reference_image is None and reference_type is not None:
                raise HTTPException(status_code=422, detail="reference_type 必須搭配 reference_image")
            if reference_type not in (None, "upper_body", "lower_body"):
                raise HTTPException(status_code=422, detail="reference_type 只支援 upper_body 或 lower_body")
            validated = None
            if reference_image is not None:
                validated = await validate_image(
                    reference_image,  # type: ignore[arg-type]
                    max_bytes=settings.image_max_upload_bytes,
                    max_pixels=settings.image_max_pixels,
                )
            return RecommendationInput(
                payload=SearchRequest.model_validate_json(raw_payload),
                reference_content=validated.content if validated is not None else None,
                reference_type=reference_type,
            )
        return RecommendationInput(payload=SearchRequest.model_validate(await request.json()))
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=json.loads(error.json())) from error
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="payload 必須是有效 JSON") from error


def uploaded_reference_item(content: bytes, garment_zone: Literal["upper_body", "lower_body"]) -> tuple[ClothResult, Path]:
    """Create a request-scoped pseudo catalog item for the ranker and VLM."""
    with tempfile.NamedTemporaryFile(
        prefix="matching-outfit-reference-", suffix=".image", delete=False
    ) as temporary:
        temporary.write(content)
        path = Path(temporary.name)
    return (
        ClothResult(
            id=-1,
            source_item_id=None,
            product_display_name="你的上傳上衣" if garment_zone == "upper_body" else "你的上傳下身",
            garment_zone=garment_zone,
            # The browser keeps the local preview. The file path is only exposed to the VLM.
            image_url="uploaded-reference",
            price=0,
            base_colour=None,
            article_type=None,
            similarity=1.0,
            is_reference=True,
            image_path=str(path),
        ),
        path,
    )


def remove_temporary_reference(path: Path) -> None:
    path.unlink(missing_ok=True)


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


def catalog_item_view(cloth: Cloth) -> CatalogItem:
    return CatalogItem(
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
        items=[catalog_item_view(cloth) for cloth in clothes],
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


def favorite_outfit_signature(item_ids: list[int]) -> str:
    return ",".join(str(item_id) for item_id in sorted(set(item_ids)))


def favorite_collection_for(db: Session, user_key: str) -> FavoriteCollection:
    rows = db.execute(
        select(UserFavoriteItem, Cloth)
        .join(Cloth, Cloth.id == UserFavoriteItem.cloth_id)
        .where(UserFavoriteItem.user_key == user_key)
        .order_by(UserFavoriteItem.created_at.desc(), UserFavoriteItem.id.desc())
    ).all()
    outfits = list(
        db.scalars(
            select(UserFavoriteOutfit)
            .where(UserFavoriteOutfit.user_key == user_key)
            .order_by(UserFavoriteOutfit.created_at.desc(), UserFavoriteOutfit.id.desc())
        )
    )
    outfit_items: dict[int, list[CatalogItem]] = {outfit.id: [] for outfit in outfits}
    if outfits:
        item_rows = db.execute(
            select(UserFavoriteOutfitItem.outfit_id, Cloth)
            .join(
                UserFavoriteItem,
                UserFavoriteItem.id == UserFavoriteOutfitItem.favorite_item_id,
            )
            .join(Cloth, Cloth.id == UserFavoriteItem.cloth_id)
            .where(
                UserFavoriteOutfitItem.outfit_id.in_([outfit.id for outfit in outfits])
            )
            .order_by(
                UserFavoriteOutfitItem.outfit_id,
                UserFavoriteOutfitItem.position,
            )
        ).all()
        for outfit_id, cloth in item_rows:
            outfit_items[outfit_id].append(catalog_item_view(cloth))

    return FavoriteCollection(
        user_key=user_key,
        items=[
            FavoriteItem(item=catalog_item_view(cloth), favorited_at=favorite.created_at)
            for favorite, cloth in rows
        ],
        outfits=[
            FavoriteOutfit(
                id=outfit.id,
                favorited_at=outfit.created_at,
                items=outfit_items[outfit.id],
            )
            for outfit in outfits
            if len(outfit_items[outfit.id]) >= 2
        ],
    )


@router.get("/favorites/{user_key}", response_model=FavoriteCollection)
def get_favorites(user_key: str, db: Session = Depends(get_db)) -> FavoriteCollection:
    return favorite_collection_for(db, user_key)


@router.put(
    "/favorites/{user_key}/items", response_model=FavoriteItemsMutationResponse
)
def update_favorite_items(
    user_key: str,
    payload: FavoriteItemsUpdate,
    db: Session = Depends(get_db),
) -> FavoriteItemsMutationResponse:
    item_ids = list(dict.fromkeys(payload.item_ids))
    found_ids = set(
        db.scalars(select(Cloth.id).where(Cloth.id.in_(item_ids))).all()
    )
    missing_ids = sorted(set(item_ids) - found_ids)
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Catalog items not found: {', '.join(map(str, missing_ids))}",
        )

    existing_rows = list(
        db.scalars(
            select(UserFavoriteItem).where(
                UserFavoriteItem.user_key == user_key,
                UserFavoriteItem.cloth_id.in_(item_ids),
            )
        )
    )
    existing_by_cloth = {row.cloth_id: row for row in existing_rows}
    existing_ids = set(existing_by_cloth)
    added = removed = 0
    if payload.favorited:
        for item_id in item_ids:
            favorite = existing_by_cloth.get(item_id)
            if favorite is None:
                db.add(
                    UserFavoriteItem(
                        user_key=user_key, cloth_id=item_id, is_direct=True
                    )
                )
                added += 1
            else:
                favorite.is_direct = True
    else:
        removed = len(existing_ids)
        if existing_ids:
            favorite_ids = [row.id for row in existing_rows]
            affected_outfit_ids = list(
                db.scalars(
                    select(UserFavoriteOutfitItem.outfit_id)
                    .where(
                        UserFavoriteOutfitItem.favorite_item_id.in_(favorite_ids)
                    )
                    .distinct()
                )
            )
            if affected_outfit_ids:
                preserved_favorite_ids = set(
                    db.scalars(
                        select(UserFavoriteOutfitItem.favorite_item_id).where(
                            UserFavoriteOutfitItem.outfit_id.in_(affected_outfit_ids),
                            UserFavoriteOutfitItem.favorite_item_id.not_in(favorite_ids),
                        )
                    )
                )
                for favorite in db.scalars(
                    select(UserFavoriteItem).where(
                        UserFavoriteItem.id.in_(preserved_favorite_ids)
                    )
                ):
                    favorite.is_direct = True
                db.execute(
                    delete(UserFavoriteOutfitItem).where(
                        UserFavoriteOutfitItem.outfit_id.in_(affected_outfit_ids)
                    )
                )
                db.execute(
                    delete(UserFavoriteOutfit).where(
                        UserFavoriteOutfit.id.in_(affected_outfit_ids)
                    )
                )
            db.execute(
                delete(UserFavoriteItem).where(
                    UserFavoriteItem.user_key == user_key,
                    UserFavoriteItem.cloth_id.in_(existing_ids),
                )
            )
    db.commit()

    favorite_item_ids = list(
        db.scalars(
            select(UserFavoriteItem.cloth_id)
            .where(UserFavoriteItem.user_key == user_key)
            .order_by(UserFavoriteItem.cloth_id)
        ).all()
    )
    return FavoriteItemsMutationResponse(
        user_key=user_key,
        added=added,
        removed=removed,
        favorite_item_ids=favorite_item_ids,
    )


@router.put("/favorites/{user_key}/outfits", response_model=FavoriteCollection)
def update_favorite_outfit(
    user_key: str,
    payload: FavoriteOutfitUpdate,
    db: Session = Depends(get_db),
) -> FavoriteCollection:
    item_ids = list(dict.fromkeys(payload.item_ids))
    found_ids = set(
        db.scalars(select(Cloth.id).where(Cloth.id.in_(item_ids))).all()
    )
    missing_ids = sorted(set(item_ids) - found_ids)
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Catalog items not found: {', '.join(map(str, missing_ids))}",
        )

    signature = favorite_outfit_signature(item_ids)
    outfit = db.scalar(
        select(UserFavoriteOutfit).where(
            UserFavoriteOutfit.user_key == user_key,
            UserFavoriteOutfit.item_signature == signature,
        )
    )
    if payload.favorited and outfit is None:
        favorite_rows = list(
            db.scalars(
                select(UserFavoriteItem).where(
                    UserFavoriteItem.user_key == user_key,
                    UserFavoriteItem.cloth_id.in_(item_ids),
                )
            )
        )
        favorites_by_cloth = {row.cloth_id: row for row in favorite_rows}
        for item_id in item_ids:
            if item_id not in favorites_by_cloth:
                favorite = UserFavoriteItem(
                    user_key=user_key, cloth_id=item_id, is_direct=False
                )
                db.add(favorite)
                favorites_by_cloth[item_id] = favorite
        db.flush()

        outfit = UserFavoriteOutfit(
            user_key=user_key,
            item_signature=signature,
        )
        db.add(outfit)
        db.flush()
        db.add_all(
            [
                UserFavoriteOutfitItem(
                    outfit_id=outfit.id,
                    favorite_item_id=favorites_by_cloth[item_id].id,
                    position=position,
                )
                for position, item_id in enumerate(item_ids)
            ]
        )
    elif not payload.favorited and outfit is not None:
        member_ids = list(
            db.scalars(
                select(UserFavoriteOutfitItem.favorite_item_id).where(
                    UserFavoriteOutfitItem.outfit_id == outfit.id
                )
            )
        )
        db.execute(
            delete(UserFavoriteOutfitItem).where(
                UserFavoriteOutfitItem.outfit_id == outfit.id
            )
        )
        db.delete(outfit)
        db.flush()

        for favorite in db.scalars(
            select(UserFavoriteItem).where(UserFavoriteItem.id.in_(member_ids))
        ):
            still_grouped = db.scalar(
                select(UserFavoriteOutfitItem.id)
                .where(UserFavoriteOutfitItem.favorite_item_id == favorite.id)
                .limit(1)
            )
            if not favorite.is_direct and still_grouped is None:
                db.delete(favorite)

    db.commit()
    return favorite_collection_for(db, user_key)


@router.post("/similarity_image", response_model=list[ClothResult])
async def similarity_image(
    image: UploadFile = File(...),
    # the number of results to return, between 1 and 50
    results: int = Query(default=12, ge=1, le=50),
    # type: upper_body, lower_body, one_piece, shoes, all
    garment_type: GarmentZone | Literal["all"] = Query(default="all", alias="type"),
    db: Session = Depends(get_db),
) -> list[ClothResult]:
    """Find similar garments, optionally within one catalog garment type."""
    # validate image size
    uploaded = await validate_image(
        image,
        max_bytes=settings.image_max_upload_bytes,
        max_pixels=settings.image_max_pixels,
    )
    return await run_in_threadpool(
        find_similar_by_image,  # find similar clothes
        db,
        uploaded.content,
        limit=results,
        garment_type=None if garment_type == "all" else garment_type,
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
    """Insert a preference sentence or merge an exact text-and-origin duplicate."""
    candidates = db.scalars(
        select(UserStylePreference).where(
            UserStylePreference.user_key == user_key,
            UserStylePreference.preference_text == row.preference_text,
        )
    ).all()
    origin_key = sorted(set(row.origin_item_ids))
    existing = next(
        (
            candidate
            for candidate in candidates
            if (
                candidate.preference_type == row.preference_type
                and sorted(set(candidate.origin_item_ids)) == origin_key
            )
        ),
        None,
    )
    now = datetime.now(timezone.utc)
    if existing is None:
        created = UserStylePreference(
            user_key=user_key,
            preference_text=row.preference_text,
            preference_type=row.preference_type,
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
                preference_type="prefer",
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


def item_preference_proposal(cloth: Cloth) -> StylePreferenceCreate:
    attributes = [
        value.strip()
        for value in (cloth.base_colour, cloth.article_type, cloth.usage)
        if value and value.strip()
    ]
    sentence = f"使用者喜歡「{cloth.product_display_name}」"
    if attributes:
        sentence += f"；偏好的商品特徵包含 {'、'.join(attributes)}"
    sentence += "。"
    if len(sentence) > 500:
        sentence = f"{sentence[:497]}..."
    return StylePreferenceCreate(
        preference_text=sentence,
        preference_type="prefer",
        source="implicit",
        origin_item_ids=[str(cloth.id)],
    )


def outfit_reaction_preference(
    clothes: list[Cloth], payload: StylePreferenceAddRequest
) -> StylePreferenceCreate:
    """Make one durable, structured preference from a Like/Dislike reaction.

    A single item reads like a catalog-page reaction (named attributes); more than
    one reads like a recommendation-card reaction (a whole outfit). Either shape
    switches its verb/label by ``preference_type`` so the sentence itself states a
    direction, since downstream matching (query planner) only reads that field.
    """
    is_avoid = payload.preference_type == "avoid"
    if len(clothes) == 1:
        cloth = clothes[0]
        attributes = [
            value.strip()
            for value in (cloth.base_colour, cloth.article_type, cloth.usage)
            if value and value.strip()
        ]
        verb = "使用者不喜歡" if is_avoid else "使用者喜歡"
        label = "應避免的商品特徵" if is_avoid else "偏好的商品特徵"
        sentence = f"{verb}「{cloth.product_display_name}」"
        if attributes:
            sentence += f"；{label}包含 {'、'.join(attributes)}"
        sentence += "。"
    else:
        outfit_description = "、".join(cloth.product_display_name for cloth in clothes)
        verb = "使用者想避免由" if is_avoid else "使用者喜歡由"
        sentence = f"{verb} {outfit_description} 組成的整套搭配。"
    user_request = (payload.user_request or "").strip()
    if user_request:
        sentence = f"在「{user_request}」的需求下，{sentence}"
    if len(sentence) > 500:
        sentence = f"{sentence[:497]}..."
    return StylePreferenceCreate(
        preference_text=sentence,
        preference_type=payload.preference_type,
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


def planning_knowledge(db: Session, raw_text: str, requirements: RequirementSummary, audience: str | None):
    # Keep the user's precise style words, not just broad summary/default fields.
    query = f"{raw_text}\n{outfit_context_embedding_text(requirements, raw_text)}"[:4000]
    try:
        return semantic_fashion_knowledge(db, query, audience=audience, top_k=12), ""
    except RuntimeError as error:
        return [], f"文章知識檢索不可用，這不是已確認的知識缺口：{error}"


def planning_context_and_knowledge(
    db: Session,
    raw_text: str,
    requirements: RequirementSummary | None,
    audience: str | None,
) -> tuple[RequirementSummary, list, str]:
    """Fetch weather while the current request performs its knowledge lookup.

    Keep ``db`` on this request thread: SQLAlchemy sessions are not thread-safe.
    Weather is network I/O, so it can run in a worker while article retrieval
    continues safely with the request-owned database session.
    """
    base_requirements = with_context_defaults(requirements)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="weather") as executor:
        weather_future = executor.submit(with_weather_context, base_requirements)
        observations, knowledge_note = planning_knowledge(
            db, raw_text, base_requirements, audience
        )
        enriched_requirements = weather_future.result()
    return enriched_requirements, observations, knowledge_note


@router.post("/query-plans", response_model=PlanResponse)
def create_query_plan(payload: PlanRequest, db: Session = Depends(get_db)) -> PlanResponse:
    planning_started = perf_counter()
    planning_timings: dict[str, float] = {}
    preference = hard_rules_for(db, payload.user_key)
    style_preferences = style_preferences_for(db, payload.user_key)
    audience = effective_audience(payload.user_input, payload.audience, preference)
    requirements, observations, knowledge_note = planning_context_and_knowledge(
        db, payload.user_input, payload.requirements, audience
    )
    planning_timings["context_and_knowledge"] = round(
        (perf_counter() - planning_started) * 1000, 1
    )
    payload = payload.model_copy(update={"requirements": requirements})
    try:
        llm = LLM()
        intent_started = perf_counter()
        intent_interpreter = FashionIntentInterpreter(llm)
        intent, fallback_used = interpret_fashion_intent_or_none(
            intent_interpreter,
            enabled=settings.fashion_intent_interpreter_enabled,
            raw_user_text=payload.user_input,
            requirement_summary=(
                payload.requirements
                or RequirementSummary(search_brief=payload.user_input)
            ),
            audience=audience,
            hard=preference,
            style_preferences=style_preferences,
            observations=observations,
        )
        planning_timings["fashion_intent"] = round(
            (perf_counter() - intent_started) * 1000, 1
        )
        planner = QueryPlanner(llm)
        query_planner_started = perf_counter()
        response = planner.plan(
            payload.user_input,
            audience=audience,
            hard=preference,
            style_preferences=style_preferences,
            requirements=payload.requirements,
            fashion_intent=intent,
            search_garment_zones=payload.search_garment_zones,
            intent_fallback_used=fallback_used,
            intent_fallback_error=intent_interpreter.last_error,
            include_debug=payload.include_debug,
            observations=observations,
            knowledge_retrieval_note=knowledge_note,
        )
        planning_timings["query_planner"] = round(
            (perf_counter() - query_planner_started) * 1000, 1
        )
        planning_timings["total"] = round(
            (perf_counter() - planning_started) * 1000, 1
        )
        if response.debug is not None:
            response = response.model_copy(update={
                "debug": response.debug.model_copy(update={
                    "stage_timings_ms": planning_timings,
                })
            })
        return response
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
        result = RequirementCollector(LLM()).collect(
            payload.messages,
            audience=audience,
            previous_requirements=payload.previous_requirements,
        )
        return result.model_copy(update={"requirements": with_weather_context(result.requirements)})
    except RuntimeError as error:
        raise HTTPException(
            status_code=503, detail=f"Requirement agent unavailable: {error}"
        ) from error


@router.post("/query-plans/refine", response_model=PlanResponse)
def refine_query_plan(payload: RefineRequest, db: Session = Depends(get_db)) -> PlanResponse:
    planning_started = perf_counter()
    planning_timings: dict[str, float] = {}
    selected = [query for query in payload.existing_queries if query.selected]
    original = payload.original_input.strip() or " ".join(query.text for query in selected)
    combined = f"{original} {payload.user_input}".strip()
    preference = hard_rules_for(db, payload.user_key)
    style_preferences = style_preferences_for(db, payload.user_key)
    audience = effective_audience(combined, payload.audience, preference)
    requirements, observations, knowledge_note = planning_context_and_knowledge(
        db, combined, payload.requirements, audience
    )
    planning_timings["context_and_knowledge"] = round(
        (perf_counter() - planning_started) * 1000, 1
    )
    payload = payload.model_copy(update={"requirements": requirements})
    try:
        llm = LLM()
        intent_started = perf_counter()
        intent_interpreter = FashionIntentInterpreter(llm)
        intent, fallback_used = interpret_fashion_intent_or_none(
            intent_interpreter,
            enabled=settings.fashion_intent_interpreter_enabled,
            raw_user_text=original or payload.user_input,
            requirement_summary=(
                payload.requirements
                or RequirementSummary(search_brief=combined)
            ),
            audience=audience,
            hard=preference,
            style_preferences=style_preferences,
            refinement=payload.user_input,
            previous_intent=payload.fashion_intent,
            observations=observations,
        )
        planning_timings["fashion_intent"] = round(
            (perf_counter() - intent_started) * 1000, 1
        )
        planner = QueryPlanner(llm)
        query_planner_started = perf_counter()
        response = planner.plan(
            original or payload.user_input,
            audience=audience,
            hard=preference,
            style_preferences=style_preferences,
            requirements=payload.requirements,
            existing_queries=selected,
            refinement=payload.user_input,
            fashion_intent=intent,
            search_garment_zones=payload.search_garment_zones,
            intent_fallback_used=fallback_used,
            intent_fallback_error=intent_interpreter.last_error,
            include_debug=payload.include_debug,
            observations=observations,
            knowledge_retrieval_note=knowledge_note,
        )
        planning_timings["query_planner"] = round(
            (perf_counter() - query_planner_started) * 1000, 1
        )
        planning_timings["total"] = round(
            (perf_counter() - planning_started) * 1000, 1
        )
        if response.debug is not None:
            response = response.model_copy(update={
                "debug": response.debug.model_copy(update={
                    "stage_timings_ms": planning_timings,
                })
            })
        return response
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
def recommendations(
    background_tasks: BackgroundTasks,
    request_input: RecommendationInput = Depends(recommendation_input),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    started_at = perf_counter()
    timings: dict[str, float] = {}

    def finalize_debug(
        trace: RecommendationDebug | None, **updates: object
    ) -> RecommendationDebug | None:
        if trace is None:
            return None
        timings["total"] = round((perf_counter() - started_at) * 1000, 1)
        return trace.model_copy(update={
            "stage_timings_ms": dict(timings),
            **updates,
        })

    payload = request_input.payload
    outfit_budget_max = (
        payload.requirements.outfit_budget_max
        if settings.outfit_budget_filter_enabled and payload.requirements is not None
        else None
    )

    def apply_outfit_budget(
        outfits: list,
    ) -> list:
        if outfit_budget_max is None:
            return outfits
        return [
            outfit for outfit in outfits
            if sum(item.price for item in outfit.items) <= outfit_budget_max
        ]

    reference_item: ClothResult | None = None
    if request_input.reference_content is not None and request_input.reference_type is not None:
        reference_item, temporary_path = uploaded_reference_item(
            request_input.reference_content, request_input.reference_type
        )
        background_tasks.add_task(remove_temporary_reference, temporary_path)
        counterpart_zone = (
            "lower_body"
            if request_input.reference_type == "upper_body"
            else "upper_body"
        )
        counterpart_queries = [
            query for query in payload.queries if query.garment_zone == counterpart_zone
        ]
        if not counterpart_queries:
            raise HTTPException(status_code=422, detail=f"沒有可用的 {counterpart_zone} 搜尋條件")
        payload = payload.model_copy(update={"queries": counterpart_queries})
    payload = payload.model_copy(update={"requirements": with_context_defaults(payload.requirements)})
    hard = hard_rules_for(db, payload.user_key)
    audience = effective_audience(payload.user_input, payload.audience, hard)
    try:
        groups = search_catalog(
            db,
            payload.queries,
            payload.top_k,
            audience=audience,
            hard=hard,
            user_input=payload.user_input,
            requirements=payload.requirements,
        )
        timings["catalog_search"] = round((perf_counter() - started_at) * 1000, 1)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Embedding search unavailable: {error}") from error
    ranked_pool = rank_outfits(
        groups,
        limit=min(750, max(200, payload.shortlist_count * 20)),
        user_context=payload.user_input,
        reference_item=reference_item,
        outfit_budget_max=outfit_budget_max,
    )
    timings["outfit_ranker"] = round((perf_counter() - started_at) * 1000 - timings["catalog_search"], 1)
    if settings.outfit_compatibility_enabled:
        compatibility_ranked, compatibility_note = rerank_outfits_by_compatibility(ranked_pool)
    else:
        compatibility_ranked, compatibility_note = ranked_pool, "disabled"
    timings["compatibility_rerank"] = round((perf_counter() - started_at) * 1000 - timings["catalog_search"] - timings["outfit_ranker"], 1)
    shortlist = compatibility_ranked[:payload.shortlist_count]
    debug = (
        RecommendationDebug(
            search_results=groups,
            ranked_candidate_count=len(ranked_pool),
            ranked_preview=compatibility_ranked[:30],
            shortlist_before_review=shortlist,
            stage_timings_ms=timings,
            compatibility_note=compatibility_note,
        )
        if payload.include_debug
        else None
    )
    if not shortlist:
        return RecommendationResponse(
            recommendations=[],
            review_note="No valid outfit combinations",
            debug=finalize_debug(debug),
        )

    # Query Planner already produced one shoe brief per A-G styling direction.
    # Map those seven briefs onto the ranked outfits without another LLM call.
    shoe_specs = {
        outfit.id: payload.shoe_specs[outfit.direction_id]
        for outfit in shortlist
        if outfit.direction_id is not None
        and outfit.direction_id in payload.shoe_specs
    }

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
        final = select_diverse(shortlist, payload.final_count)
        shoe_retrieval_started = perf_counter()
        shoe_result = attach_post_review_shoes(
            db, final, shoe_specs, audience=audience, hard=hard,
            requirements=payload.requirements, user_input=payload.user_input,
            include_debug=debug is not None,
        )
        timings["shoe_retrieval"] = round((perf_counter() - shoe_retrieval_started) * 1000, 1)
        if debug is not None:
            final, shoe_retrievals = shoe_result
        else:
            final = shoe_result
        final = apply_outfit_budget(final)
        final_ids = {recommendation.id for recommendation in final}
        if debug is not None:
            debug = finalize_debug(
                debug,
                aesthetic_review_error=note,
                shoe_retrievals=shoe_retrievals,
            )
        return RecommendationResponse(
            recommendations=final,
            discarded_recommendations=[
                recommendation
                for recommendation in shortlist
                if recommendation.id not in final_ids
            ],
            aesthetic_reviewed=False,
            review_note=note,
            debug=debug,
        )

    if debug is not None:
        debug = debug.model_copy(
            update={
                # Article knowledge is used while planning.  The visual
                # reviewer judges only the candidate images and the approved
                # request context, so it cannot be biased by article text.
                "knowledge_observations": [],
                "aesthetic_review_attempted": True,
            }
        )

    style_preferences = style_preferences_for(db, payload.user_key)
    preference_context = build_planner_preference_context(hard, style_preferences)
    reviewer = None
    review_started = perf_counter()
    try:
        reviewer = AestheticReviewer(LLM())
        reviews = reviewer.review(
            payload.user_input,
            shortlist,
            user_preferences=preference_context,
            styling_guide=payload.styling_guide,
            requirements=payload.requirements,
            fashion_intent=payload.fashion_intent,
        )
        reviewed_pool = apply_aesthetic_reviews(
            shortlist,
            reviews,
            final_count=len(shortlist),
            fashion_intent=payload.fashion_intent,
        )
        timings["aesthetic_review"] = round((perf_counter() - review_started) * 1000, 1)
        diagnostics = getattr(reviewer, "last_debug", {})
        if debug is not None:
            debug = debug.model_copy(update={"aesthetic_review_diagnostics": diagnostics})
        eligible = [
            recommendation
            for recommendation in reviewed_pool
            if recommendation.aesthetic_review is not None
            and not recommendation.aesthetic_review.fatal_issues
        ]
        # Preserve the reviewer's 100%-review-based ordering while avoiding a
        # page full of the same shirt or trousers when distinct products exist.
        final = select_diverse(eligible, payload.final_count)
        shoe_retrieval_started = perf_counter()
        shoe_result = attach_post_review_shoes(
            db,
            final,
            shoe_specs,
            audience=audience,
            hard=hard,
            requirements=payload.requirements,
            user_input=payload.user_input,
            include_debug=debug is not None,
        )
        timings["shoe_retrieval"] = round((perf_counter() - shoe_retrieval_started) * 1000, 1)
        if debug is not None:
            final, shoe_retrievals = shoe_result
        else:
            final = shoe_result
        final = apply_outfit_budget(final)
        reviewed_count = sum(
            recommendation.aesthetic_review is not None
            for recommendation in reviewed_pool
        )
        missing_count = len(shortlist) - reviewed_count
        review_note = f"已完成 {reviewed_count}/{len(shortlist)} 套圖片美感審查，推薦 {len(final)} 套。"
        if missing_count:
            image_failed = len(diagnostics.get("image_failures", []))
            model_missing = len(diagnostics.get("missing_ids", []))
            review_note += (
                f" {missing_count} 套未完成審查，不列入最終推薦。"
                f"圖片失敗 {image_failed} 套；補審後仍缺評分 {model_missing} 套。"
            )
            if debug is not None:
                debug = debug.model_copy(update={"aesthetic_review_error": review_note})
        final_ids = {recommendation.id for recommendation in final}
        discarded = [
            recommendation
            for recommendation in reviewed_pool
            if recommendation.id not in final_ids
        ]
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
            discarded_recommendations=discarded,
            aesthetic_reviewed=True,
            review_note=review_note,
            knowledge_observation_count=len(used_observation_ids),
            knowledge_sources=knowledge_sources,
            knowledge_note="",
            debug=finalize_debug(debug, shoe_retrievals=shoe_retrievals if debug is not None else []),
        )
    except RuntimeError as error:
        final = select_diverse(shortlist, payload.final_count)
        timings["aesthetic_review"] = round((perf_counter() - review_started) * 1000, 1)
        shoe_retrieval_started = perf_counter()
        shoe_result = attach_post_review_shoes(
            db,
            final,
            shoe_specs,
            audience=audience,
            hard=hard,
            requirements=payload.requirements,
            user_input=payload.user_input,
            include_debug=debug is not None,
        )
        timings["shoe_retrieval"] = round((perf_counter() - shoe_retrieval_started) * 1000, 1)
        if debug is not None:
            final, shoe_retrievals = shoe_result
        else:
            final = shoe_result
        final = apply_outfit_budget(final)
        final_ids = {recommendation.id for recommendation in final}
        if debug is not None:
            debug = debug.model_copy(update={
                "aesthetic_review_error": str(error),
                "aesthetic_review_diagnostics": getattr(reviewer, "last_debug", {}),
                "shoe_retrievals": shoe_retrievals,
            })
        return RecommendationResponse(
            recommendations=final,
            discarded_recommendations=[
                recommendation
                for recommendation in shortlist
                if recommendation.id not in final_ids
            ],
            aesthetic_reviewed=False,
            review_note=f"Aesthetic review unavailable; match ranking used instead: {error}",
            knowledge_note="",
            debug=finalize_debug(debug, shoe_retrievals=shoe_retrievals if debug is not None else []),
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


@router.post("/preferences/{user_key}/soft/create", response_model=StylePreferenceView, status_code=201)
def add_style_preference(
    user_key: str, payload: StylePreferenceCreate, db: Session = Depends(get_db)
) -> StylePreferenceView:
    """Add one user-authored (explicit) soft preference, or merge into its slot."""
    row, _ = upsert_style_preference(db, user_key, payload)
    db.commit()
    db.refresh(row)
    return StylePreferenceView.model_validate(row)


@router.post(
    "/preferences/{user_key}/soft/add",
    response_model=StylePreferenceView,
    status_code=201,
)
def add_outfit_reaction(
    user_key: str,
    payload: StylePreferenceAddRequest,
    db: Session = Depends(get_db),
) -> StylePreferenceView:
    """Persist one explicit Like/Dislike reaction without a proposal step."""
    if payload.user_key != user_key:
        raise HTTPException(status_code=400, detail="user_key in path and body must match")
    item_ids = list(dict.fromkeys(payload.outfit_item_ids))
    clothes_by_id = {
        cloth.id: cloth
        for cloth in db.scalars(select(Cloth).where(Cloth.id.in_(item_ids))).all()
    }
    missing = [item_id for item_id in item_ids if item_id not in clothes_by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Catalog items not found: {', '.join(map(str, missing))}",
        )
    row = outfit_reaction_preference(
        [clothes_by_id[item_id] for item_id in item_ids], payload
    )
    saved, _ = upsert_style_preference(db, user_key, row, confirmed=True)
    db.commit()
    db.refresh(saved)
    return StylePreferenceView.model_validate(saved)


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


@router.delete("/preferences/{user_key}/soft/remove/{preference_id}", status_code=204)
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
    "/preferences/{user_key}/soft/from-item", response_model=StylePreferenceProposal
)
def propose_style_preference_from_item(
    user_key: str,
    payload: StylePreferenceItemProposalRequest,
    db: Session = Depends(get_db),
) -> StylePreferenceProposal:
    cloth = db.get(Cloth, payload.item_id)
    if cloth is None:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    return StylePreferenceProposal(
        proposals=[item_preference_proposal(cloth)],
        explanation="確認後會把這件商品的名稱與特徵加入偏好。",
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
