"""Portable, deterministic snapshots for sharing processed fashion knowledge."""

import base64
import hashlib
import json
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.fashion_knowledge import FashionArticle, FashionObservation
from app.schemas.fashion_knowledge import (
    FashionKnowledgeSnapshot,
    FashionKnowledgeSnapshotArticle,
    FashionKnowledgeSnapshotObservation,
)

SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SnapshotComparison:
    missing_urls: list[str]
    outdated_urls: list[str]
    local_only_urls: list[str]

    @property
    def is_behind(self) -> bool:
        return bool(self.missing_urls or self.outdated_urls)


def encode_embedding(values: list[float] | None) -> str | None:
    if values is None:
        return None
    packed = struct.pack(f"<{len(values)}f", *(float(value) for value in values))
    return base64.b64encode(packed).decode("ascii")


def decode_embedding(value: str | None, dimensions: int) -> list[float] | None:
    if value is None:
        return None
    try:
        packed = base64.b64decode(value, validate=True)
    except ValueError as error:
        raise ValueError("Snapshot contains an invalid Base64 embedding") from error
    expected_size = dimensions * 4
    if len(packed) != expected_size:
        raise ValueError(
            f"Snapshot embedding has {len(packed)} bytes; expected {expected_size}"
        )
    return list(struct.unpack(f"<{dimensions}f", packed))


def _content_payload(
    articles: list[FashionKnowledgeSnapshotArticle], embedding_dimensions: int
) -> dict:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "embedding_dimensions": embedding_dimensions,
        "articles": [article.model_dump(mode="json") for article in articles],
    }


def content_digest(
    articles: list[FashionKnowledgeSnapshotArticle], embedding_dimensions: int
) -> str:
    canonical = json.dumps(
        _content_payload(articles, embedding_dimensions),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _observation_snapshot(row: FashionObservation) -> FashionKnowledgeSnapshotObservation:
    return FashionKnowledgeSnapshotObservation(
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
        embedding_base64=encode_embedding(row.embedding),
        embedding_model=row.embedding_model,
        is_active=row.is_active,
        reviewed_at=row.reviewed_at,
    )


def build_snapshot(db: Session, embedding_dimensions: int) -> FashionKnowledgeSnapshot:
    rows = db.scalars(
        select(FashionArticle)
        .options(selectinload(FashionArticle.observations))
        .order_by(FashionArticle.source_url)
    ).all()
    articles = [
        FashionKnowledgeSnapshotArticle(
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
            extracted_at=row.extracted_at,
            observations=[
                _observation_snapshot(observation)
                for observation in sorted(
                    row.observations, key=lambda item: item.observation_id
                )
            ],
        )
        for row in rows
    ]
    return FashionKnowledgeSnapshot(
        generated_at=datetime.now(timezone.utc),
        embedding_dimensions=embedding_dimensions,
        content_digest=content_digest(articles, embedding_dimensions),
        articles=articles,
    )


def validate_snapshot(snapshot: FashionKnowledgeSnapshot) -> None:
    expected = content_digest(snapshot.articles, snapshot.embedding_dimensions)
    if snapshot.content_digest != expected:
        raise ValueError("Snapshot checksum does not match its content")
    article_urls = [article.source_url for article in snapshot.articles]
    if len(article_urls) != len(set(article_urls)):
        raise ValueError("Snapshot contains duplicate article URLs")
    observation_ids = [
        observation.observation_id
        for article in snapshot.articles
        for observation in article.observations
    ]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("Snapshot contains duplicate observation IDs")
    for article in snapshot.articles:
        for observation in article.observations:
            decode_embedding(observation.embedding_base64, snapshot.embedding_dimensions)


def load_snapshot(path: Path) -> FashionKnowledgeSnapshot:
    snapshot = FashionKnowledgeSnapshot.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    validate_snapshot(snapshot)
    return snapshot


def write_snapshot(path: Path, snapshot: FashionKnowledgeSnapshot) -> bool:
    validate_snapshot(snapshot)
    if path.exists():
        try:
            current = load_snapshot(path)
        except (ValueError, OSError):
            current = None
        if current and current.content_digest == snapshot.content_digest:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)
    return True


def _article_comparable(article: FashionKnowledgeSnapshotArticle) -> dict:
    return article.model_dump(mode="json")


def compare_snapshot(
    db: Session,
    snapshot: FashionKnowledgeSnapshot,
    embedding_dimensions: int,
) -> SnapshotComparison:
    local = build_snapshot(db, embedding_dimensions)
    incoming_by_url = {article.source_url: article for article in snapshot.articles}
    local_by_url = {article.source_url: article for article in local.articles}
    missing_urls = sorted(set(incoming_by_url) - set(local_by_url))
    local_only_urls = sorted(set(local_by_url) - set(incoming_by_url))
    outdated_urls = sorted(
        url
        for url in set(incoming_by_url) & set(local_by_url)
        if _article_comparable(incoming_by_url[url])
        != _article_comparable(local_by_url[url])
    )
    return SnapshotComparison(missing_urls, outdated_urls, local_only_urls)


def _copy_observation(
    row: FashionObservation,
    source: FashionKnowledgeSnapshotObservation,
    embedding_dimensions: int,
) -> None:
    for field in (
        "summary",
        "evidence",
        "audiences",
        "occasions",
        "climates",
        "seasons",
        "times_of_day",
        "formalities",
        "activities",
        "styles",
        "garments",
        "colors",
        "materials",
        "silhouettes",
        "styling_actions",
        "avoid_when",
        "signal_type",
        "confidence",
        "embedding_model",
        "is_active",
        "reviewed_at",
    ):
        setattr(row, field, getattr(source, field))
    row.embedding = decode_embedding(source.embedding_base64, embedding_dimensions)


def apply_snapshot(
    db: Session,
    snapshot: FashionKnowledgeSnapshot,
    comparison: SnapshotComparison,
) -> tuple[int, int]:
    validate_snapshot(snapshot)
    target_urls = set(comparison.missing_urls) | set(comparison.outdated_urls)
    if not target_urls:
        return 0, 0
    articles_applied = 0
    observations_applied = 0
    try:
        for source in snapshot.articles:
            if source.source_url not in target_urls:
                continue
            article = db.scalar(
                select(FashionArticle).where(
                    FashionArticle.source_url == source.source_url
                )
            )
            if article is None:
                article = FashionArticle(source_url=source.source_url)
                db.add(article)
            for field in (
                "source_name",
                "title",
                "author",
                "published_at",
                "collected_at",
                "language",
                "article_summary",
                "extraction_notes",
                "extraction_model",
                "extracted_at",
            ):
                setattr(article, field, getattr(source, field))
            db.flush()
            existing = {
                row.observation_id: row
                for row in db.scalars(
                    select(FashionObservation).where(
                        FashionObservation.article_id == article.id
                    )
                )
            }
            incoming_ids = {
                observation.observation_id for observation in source.observations
            }
            for observation in source.observations:
                row = existing.get(observation.observation_id)
                if row is None:
                    row = FashionObservation(
                        observation_id=observation.observation_id,
                        article_id=article.id,
                    )
                    db.add(row)
                _copy_observation(row, observation, snapshot.embedding_dimensions)
                observations_applied += 1
            for observation_id, stale in existing.items():
                if observation_id not in incoming_ids:
                    db.delete(stale)
            articles_applied += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return articles_applied, observations_applied
