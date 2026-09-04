from itertools import product
from uuid import uuid4

from app.schemas import OutfitRecommendation, QuerySearchResult


def rank_outfits(groups: list[QuerySearchResult], limit: int = 8) -> list[OutfitRecommendation]:
    by_zone = {group.query.garment_zone: group.clothes for group in groups}
    recommendations: list[OutfitRecommendation] = []

    for upper, lower in product(by_zone.get("upper_body", [])[:5], by_zone.get("lower_body", [])[:5]):
        score = (upper.similarity + lower.similarity) / 2
        recommendations.append(
            OutfitRecommendation(
                id=str(uuid4()),
                kind="separates",
                items=[upper, lower],
                score=round(score, 4),
                reasons=["Strong average text-image similarity", "Upper and lower body coverage"],
            )
        )

    for item in by_zone.get("one_piece", []):
        recommendations.append(
            OutfitRecommendation(
                id=str(uuid4()),
                kind="one_piece",
                items=[item],
                score=item.similarity,
                reasons=["Matches the selected one-piece query"],
            )
        )
    return sorted(recommendations, key=lambda result: result.score, reverse=True)[:limit]
