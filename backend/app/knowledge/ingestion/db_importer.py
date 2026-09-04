from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fashion_knowledge import FashionArticle, FashionObservation
from app.schemas.fashion_knowledge import KnowledgeRecord, OutfitObservation
from app.services.integration_tools.text_embeddings import TextEmbeddingService


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
