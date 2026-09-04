from app.schemas import AestheticReview
from app.services.aesthetic_reviewer import apply_aesthetic_reviews
from tests.test_outfit_ranker import cloth, group
from app.services.outfit_ranker import rank_outfits


def test_aesthetic_review_changes_final_score_and_is_attached() -> None:
    recommendation = rank_outfits(
        [
            group("upper_body", [cloth(1, "upper_body", "White", 0.8)]),
            group("lower_body", [cloth(2, "lower_body", "Black", 0.8)]),
        ],
        limit=1,
    )[0]
    review = AestheticReview(
        occasion_fit=90,
        color_harmony=92,
        silhouette_balance=84,
        material_coherence=82,
        overall_aesthetic=90,
        reason="配色乾淨，輪廓協調。",
    )

    result = apply_aesthetic_reviews(
        [recommendation], {recommendation.id: review}, final_count=1
    )[0]

    assert result.aesthetic_review == review
    assert result.score_breakdown is not None
    assert result.score_breakdown.aesthetic is not None
    assert result.score != recommendation.score
    assert review.reason in result.reasons
