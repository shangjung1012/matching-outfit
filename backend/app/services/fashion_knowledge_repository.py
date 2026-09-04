from datetime import datetime
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fashion_knowledge import FashionArticle, FashionObservation
from app.schemas.styling import KnowledgeRecord, OutfitObservation
from app.services.text_embeddings import TextEmbeddingService


AUDIENCE_BY_SOURCE = {
    "elle.com": ["women"],
    "marieclairekorea.com": ["women"],
    "gq.com.tw": ["men"],
    "gqkorea.co.kr": ["men"],
}


def parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def observation_audiences(observation: OutfitObservation, source_name: str) -> list[str]:
    if observation.audiences:
        return list(dict.fromkeys(observation.audiences))
    return AUDIENCE_BY_SOURCE.get(source_name.lower(), ["unisex"])


def observation_embedding_text(observation: OutfitObservation, audiences: list[str]) -> str:
    sections = [
        ("audiences", audiences),
        ("summary", [observation.summary]),
        ("evidence", [observation.evidence]),
        ("occasions", observation.occasions),
        ("climates", observation.climates),
        ("seasons", observation.seasons),
        ("styles", observation.styles),
        ("garments", observation.garments),
        ("colors", observation.colors),
        ("materials", observation.materials),
        ("silhouettes", observation.silhouettes),
        ("styling actions", observation.styling_actions),
        ("avoid when", observation.avoid_when),
        ("signal type", [observation.signal_type]),
    ]
    return "\n".join(f"{label}: {', '.join(values)}" for label, values in sections if values)


def import_knowledge_records(
    db: Session,
    records: list[KnowledgeRecord],
    embedder: TextEmbeddingService,
    *,
    refresh_embeddings: bool = False,
) -> tuple[int, int, int]:
    article_count = 0
    observation_count = 0
    pending_embeddings: list[tuple[FashionObservation, str]] = []

    for record in records:
        article = db.scalar(
            select(FashionArticle).where(FashionArticle.source_url == record.article.source_url)
        )
        if article is None:
            article = FashionArticle(source_url=record.article.source_url)
            db.add(article)
        article.source_name = record.article.source_name
        article.title = record.article.title
        article.author = record.article.author
        article.published_at = parse_optional_datetime(record.article.published_at)
        article.collected_at = record.article.collected_at
        article.language = record.article.language
        article.article_summary = record.extraction.article_summary
        article.extraction_notes = record.extraction.extraction_notes
        article.extraction_model = record.extraction_model
        article.extracted_at = record.extracted_at
        db.flush()

        existing = {
            item.observation_id: item
            for item in db.scalars(
                select(FashionObservation).where(FashionObservation.article_id == article.id)
            )
        }
        incoming_ids: set[str] = set()
        for observation in record.extraction.observations:
            incoming_ids.add(observation.observation_id)
            row = existing.get(observation.observation_id)
            if row is None:
                row = FashionObservation(
                    observation_id=observation.observation_id,
                    article_id=article.id,
                )
                db.add(row)
            audiences = observation_audiences(observation, record.article.source_name)
            row.summary = observation.summary
            row.evidence = observation.evidence
            row.audiences = audiences
            row.occasions = observation.occasions
            row.climates = observation.climates
            row.seasons = observation.seasons
            row.styles = observation.styles
            row.garments = observation.garments
            row.colors = observation.colors
            row.materials = observation.materials
            row.silhouettes = observation.silhouettes
            row.styling_actions = observation.styling_actions
            row.avoid_when = observation.avoid_when
            row.signal_type = observation.signal_type
            row.confidence = observation.confidence
            if refresh_embeddings or row.embedding is None or row.embedding_model != embedder.model:
                pending_embeddings.append(
                    (row, observation_embedding_text(observation, audiences))
                )
            observation_count += 1

        for observation_id, stale in existing.items():
            if observation_id not in incoming_ids:
                db.delete(stale)
        article_count += 1

    db.flush()
    vectors = embedder.encode([text for _, text in pending_embeddings])
    for (row, _), vector in zip(pending_embeddings, vectors, strict=True):
        row.embedding = vector
        row.embedding_model = embedder.model
    db.commit()
    return article_count, observation_count, len(pending_embeddings)


def infer_audience(query: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    lowered = query.lower()
    if any(term in lowered for term in ("男生", "男性", "男裝")) or re.search(
        r"\b(men|man|menswear)\b", lowered
    ):
        return "men"
    if any(term in lowered for term in ("女生", "女性", "女裝")) or re.search(
        r"\b(women|woman|womenswear)\b", lowered
    ):
        return "women"
    return None


def retrieve_observations_from_db(
    db: Session,
    query: str,
    top_k: int,
    embedder: TextEmbeddingService,
    *,
    audience: str | None = None,
) -> list[OutfitObservation]:
    query_vector = embedder.encode([query])[0]
    candidate_limit = max(50, top_k * 10)
    candidates = db.scalars(
        select(FashionObservation)
        .where(
            FashionObservation.is_active.is_(True),
            FashionObservation.embedding.is_not(None),
            FashionObservation.embedding_model == embedder.model,
        )
        .order_by(FashionObservation.embedding.cosine_distance(query_vector))
        .limit(candidate_limit)
    ).all()
    requested_audience = infer_audience(query, audience)
    if requested_audience:
        candidates = [
            item
            for item in candidates
            if requested_audience in item.audiences or "unisex" in item.audiences
        ]

    return [
        OutfitObservation(
            observation_id=item.observation_id,
            source_url=item.article.source_url,
            source_name=item.article.source_name,
            source_title=item.article.title,
            published_at=(item.article.published_at.isoformat() if item.article.published_at else None),
            summary=item.summary,
            evidence=item.evidence,
            audiences=item.audiences,
            occasions=item.occasions,
            climates=item.climates,
            seasons=item.seasons,
            styles=item.styles,
            garments=item.garments,
            colors=item.colors,
            materials=item.materials,
            silhouettes=item.silhouettes,
            styling_actions=item.styling_actions,
            avoid_when=item.avoid_when,
            signal_type=item.signal_type,
            confidence=item.confidence,
        )
        for item in candidates[:top_k]
    ]
