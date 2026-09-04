import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fashion_knowledge import FashionObservation
from app.schemas.fashion_knowledge import OutfitObservation
from app.services.integration_tools.text_embeddings import TextEmbeddingService


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    latin = set(re.findall(r"[a-z0-9][a-z0-9_-]+", lowered))
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", lowered)
    cjk = {
        run[index : index + 2]
        for run in cjk_runs
        for index in range(max(1, len(run) - 1))
        if run[index : index + 2]
    }
    return latin | cjk


def retrieve_observations(
    query: str, observations: list[OutfitObservation], top_k: int
) -> list[OutfitObservation]:
    query_tokens = _tokens(query)
    ranked: list[tuple[float, OutfitObservation]] = []
    for observation in observations:
        searchable = " ".join(
            [
                observation.summary,
                *observation.occasions,
                *observation.climates,
                *observation.seasons,
                *observation.times_of_day,
                *observation.formalities,
                *observation.activities,
                *observation.styles,
                *observation.garments,
                *observation.colors,
                *observation.materials,
                *observation.silhouettes,
                *observation.styling_actions,
                *observation.avoid_when,
            ]
        )
        overlap = len(query_tokens & _tokens(searchable))
        score = overlap * 2.0 + observation.confidence
        if observation.signal_type == "timeless":
            score += 0.25
        ranked.append((score, observation))
    ranked.sort(key=lambda item: item[0], reverse=True)
    positive = [item for item in ranked if item[0] > 0.5]
    return [observation for _, observation in (positive or ranked)[:top_k]]


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
            times_of_day=item.times_of_day,
            formalities=item.formalities,
            activities=item.activities,
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
