from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import get_db
from app.knowledge.ingestion.article_collector import ArticleCollector
from app.knowledge.ingestion.article_discovery import (
    SOURCE_BY_KEY,
    SOURCES,
    ArticleDiscovery,
    discover_new_articles,
)
from app.knowledge.ingestion.article_extractor import ArticleKnowledgeExtractor
from app.knowledge.ingestion.import_input import normalize_article_url, normalize_hostname, allowed_domain, parse_import_input
from urllib.parse import urlsplit
from app.knowledge.ingestion.db_importer import import_knowledge_records
from app.knowledge.store import FashionKnowledgeStore
from app.models.fashion_knowledge import FashionArticle, FashionObservation
from app.schemas.fashion_knowledge import (
    FashionArticleAdminView,
    FashionArticleAutoUpdateRequest,
    FashionArticleAutoUpdateResponse,
    FashionArticleCollectRequest,
    FashionArticleCollectResponse,
    FashionArticleCollectResult,
    FashionArticleList,
    FashionObservationAdminView,
    FashionObservationPatch,
    FashionKnowledgeSourceView,
)
from app.services.integration_tools.llm import LLM
from app.services.integration_tools.text_embeddings import TextEmbeddingService


router = APIRouter(prefix="/fashion-knowledge", tags=["fashion knowledge admin"])


def _require_api_key() -> None:
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY 尚未設定，無法將文章整理成繁體中文搭配知識。",
        )


def _observation_view(row: FashionObservation) -> FashionObservationAdminView:
    return FashionObservationAdminView(
        id=row.id,
        observation_id=row.observation_id,
        summary=row.summary,
        evidence=row.evidence,
        audiences=row.audiences or [],
        occasions=row.occasions or [],
        climates=row.climates or [],
        seasons=row.seasons or [],
        times_of_day=row.times_of_day or [],
        formalities=row.formalities or [],
        activities=row.activities or [],
        styles=row.styles or [],
        garments=row.garments or [],
        colors=row.colors or [],
        materials=row.materials or [],
        silhouettes=row.silhouettes or [],
        styling_actions=row.styling_actions or [],
        avoid_when=row.avoid_when or [],
        signal_type=row.signal_type,
        confidence=row.confidence,
        is_active=row.is_active,
        has_embedding=row.embedding is not None,
    )


def _article_view(row: FashionArticle) -> FashionArticleAdminView:
    observations = sorted(row.observations, key=lambda item: item.id)
    return FashionArticleAdminView(
        id=row.id,
        source_url=row.source_url,
        source_name=row.source_name,
        title=row.title,
        author=row.author,
        published_at=row.published_at,
        collected_at=row.collected_at,
        language=row.language,
        article_summary=row.article_summary,
        extraction_notes=row.extraction_notes or [],
        extraction_model=row.extraction_model,
        observation_count=len(observations),
        active_observation_count=sum(item.is_active for item in observations),
        observations=[_observation_view(item) for item in observations],
    )


@router.get("/articles", response_model=FashionArticleList)
def list_articles(
    search: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> FashionArticleList:
    filters = []
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                FashionArticle.title.ilike(term),
                FashionArticle.source_name.ilike(term),
                FashionArticle.article_summary.ilike(term),
            )
        )
    total_query = select(func.count()).select_from(FashionArticle)
    rows_query = (
        select(FashionArticle)
        .options(selectinload(FashionArticle.observations))
        .order_by(FashionArticle.collected_at.desc(), FashionArticle.id.desc())
        .offset(offset)
        .limit(limit)
    )
    if filters:
        total_query = total_query.where(*filters)
        rows_query = rows_query.where(*filters)
    return FashionArticleList(
        items=[_article_view(row) for row in db.scalars(rows_query).all()],
        total=db.scalar(total_query) or 0,
    )


def _collect_urls(
    db: Session,
    urls: list[str],
    *,
    download_images: bool = False,
    max_images: int = 4,
    raw_text: str = "",
    force_refresh: bool = False,
) -> FashionArticleCollectResponse:
    _require_api_key()
    entries = [(url, "") for url in urls] + parse_import_input(raw_text)
    if not entries:
        raise HTTPException(status_code=422, detail="請至少輸入一個文章網址。")
    store = FashionKnowledgeStore(settings.article_data_dir)
    collector = ArticleCollector(settings.allowed_article_domains, settings.article_user_agent)
    extractor = ArticleKnowledgeExtractor(LLM())
    embedder = TextEmbeddingService(
        settings.openai_api_key,
        settings.knowledge_embedding_model,
        settings.knowledge_embedding_dimensions,
    )
    results: list[FashionArticleCollectResult] = []
    seen: set[str] = set()
    internal_hosts = {normalize_hostname(urlsplit(origin).hostname or "") for origin in settings.cors_origins}
    known = {}
    for row in db.scalars(select(FashionArticle)).all():
        try:
            known[normalize_article_url(row.source_url)] = row
        except ValueError:
            continue
    for raw_url, category in entries:
        try:
            url = normalize_article_url(raw_url, internal_hosts)
        except ValueError as error:
            results.append(FashionArticleCollectResult(url=raw_url, category=category, status="skipped", message=str(error)))
            continue
        if url in seen:
            results.append(FashionArticleCollectResult(url=url, category=category, status="skipped", message="略過重複網址"))
            continue
        seen.add(url)
        if not allowed_domain(url, settings.allowed_article_domains):
            results.append(FashionArticleCollectResult(url=url, category=category, status="unsupported", message="網域尚未開放"))
            continue
        if url in known and not force_refresh:
            results.append(FashionArticleCollectResult(url=url, category=category, status="skipped", article_id=known[url].id, message="已收錄，不重複消耗 LLM 用量"))
            continue
        try:
            article = collector.collect(url)
            existing = db.scalar(
                select(FashionArticle).where(
                    FashionArticle.source_url.in_([url, article.source_url])
                )
            )
            if existing and not force_refresh:
                results.append(FashionArticleCollectResult(url=url, category=category, status="skipped", article_id=existing.id, message="轉址後文章已收錄"))
                continue
            if download_images:
                image_dir = store.images_dir / article.source_name.replace(".", "_")
                article = collector.download_images(
                    article, image_dir, max_images=max_images
                )
            store.save_collected(article)
            record = extractor.extract(article)
            if category:
                record.extraction.extraction_notes.append(f"匯入分類：{category}")
            store.save_record(record)
            _, observation_count, _ = import_knowledge_records(db, [record], embedder)
            imported = db.scalar(
                select(FashionArticle).where(FashionArticle.source_url == record.article.source_url)
            )
            results.append(
                FashionArticleCollectResult(
                    url=url,
                    category=category,
                    status="updated" if existing else "created",
                    article_id=imported.id if imported else None,
                    title=record.article.title,
                    observation_count=observation_count,
                    message="已重新抓取並更新" if existing else "已抓取並匯入",
                )
            )
        except Exception as error:
            db.rollback()
            results.append(
                FashionArticleCollectResult(
                    url=url,
                    category=category,
                    status="failed",
                    message=str(error),
                )
            )
    return FashionArticleCollectResponse(
        results=results,
        succeeded=sum(item.status in {"created", "updated"} for item in results),
        failed=sum(item.status == "failed" for item in results),
        skipped=sum(item.status == "skipped" for item in results),
        unsupported=sum(item.status == "unsupported" for item in results),
    )


@router.get("/sources", response_model=list[FashionKnowledgeSourceView])
def list_sources() -> list[FashionKnowledgeSourceView]:
    return [
        FashionKnowledgeSourceView(
            key=source.key,
            name=source.name,
            index_url=source.index_url,
            audience=source.audience,
        )
        for source in SOURCES
    ]


@router.post("/articles/collect", response_model=FashionArticleCollectResponse)
def collect_articles(
    request: FashionArticleCollectRequest,
    db: Session = Depends(get_db),
) -> FashionArticleCollectResponse:
    return _collect_urls(
        db,
        request.urls,
        download_images=request.download_images,
        max_images=request.max_images,
        raw_text=request.raw_text,
        force_refresh=request.force_refresh,
    )


@router.post("/articles/auto-update", response_model=FashionArticleAutoUpdateResponse)
def auto_update_articles(
    request: FashionArticleAutoUpdateRequest,
    db: Session = Depends(get_db),
) -> FashionArticleAutoUpdateResponse:
    _require_api_key()
    unknown_keys = set(request.source_keys) - set(SOURCE_BY_KEY)
    if unknown_keys:
        raise HTTPException(
            status_code=422,
            detail=f"不支援的文章來源：{', '.join(sorted(unknown_keys))}",
        )
    sources = (
        [SOURCE_BY_KEY[key] for key in request.source_keys]
        if request.source_keys
        else list(SOURCES)
    )
    known_urls = set(db.scalars(select(FashionArticle.source_url)))
    collector = ArticleCollector(settings.allowed_article_domains, settings.article_user_agent)
    discovery = ArticleDiscovery(collector)
    discovery_batch = discover_new_articles(
        discovery,
        sources,
        known_urls,
        page_limit=request.page_limit,
        per_source_limit=request.per_source_limit,
        max_articles=request.max_articles,
    )
    candidates = [article.url for article in discovery_batch.articles]
    batch = (
        _collect_urls(db, candidates)
        if candidates
        else FashionArticleCollectResponse(results=[], succeeded=0, failed=0)
    )
    return FashionArticleAutoUpdateResponse(
        discovered=len(candidates),
        skipped_existing=discovery_batch.skipped_existing,
        candidates=candidates,
        discovery_errors=discovery_batch.errors,
        results=batch.results,
        succeeded=batch.succeeded,
        failed=batch.failed,
    )


@router.patch(
    "/observations/{observation_id}", response_model=FashionObservationAdminView
)
def update_observation(
    observation_id: int,
    patch: FashionObservationPatch,
    db: Session = Depends(get_db),
) -> FashionObservationAdminView:
    row = db.get(FashionObservation, observation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到這條參考句子。")
    row.is_active = patch.is_active
    db.commit()
    db.refresh(row)
    return _observation_view(row)


@router.delete("/articles/{article_id}", status_code=204)
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
) -> Response:
    article = db.get(FashionArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="找不到這篇文章。")
    source_url = article.source_url
    db.delete(article)
    db.commit()
    FashionKnowledgeStore(settings.article_data_dir).delete_article_files(source_url)
    return Response(status_code=204)
