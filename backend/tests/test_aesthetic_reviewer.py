from app.schemas import AestheticReview
from app.schemas.fashion_knowledge import OutfitObservation
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
        inner_layer_suggestion="內可穿同色系圓領短袖上衣，選擇輕薄平滑材質。",
    )

    result = apply_aesthetic_reviews(
        [recommendation], {recommendation.id: review}, final_count=1
    )[0]

    assert result.aesthetic_review == review
    assert result.aesthetic_review.inner_layer_suggestion == review.inner_layer_suggestion
    assert result.score_breakdown is not None
    assert result.score_breakdown.aesthetic is not None
    assert result.score == 0.9
    assert review.reason in result.reasons


def test_final_order_uses_only_reviewer_score() -> None:
    recommendations = rank_outfits(
        [
            group("upper_body", [
                cloth(1, "upper_body", "White", 0.99),
                cloth(2, "upper_body", "Blue", 0.60),
            ]),
            group("lower_body", [cloth(3, "lower_body", "Black", 0.80)]),
        ],
        limit=2,
    )
    high_ranker, low_ranker = recommendations
    reviews = {
        high_ranker.id: AestheticReview(
            occasion_fit=40,
            color_harmony=40,
            silhouette_balance=40,
            material_coherence=40,
            overall_aesthetic=40,
            reason="視覺協調度較低。",
        ),
        low_ranker.id: AestheticReview(
            occasion_fit=90,
            color_harmony=90,
            silhouette_balance=90,
            material_coherence=90,
            overall_aesthetic=90,
            reason="視覺協調度較高。",
        ),
    }

    result = apply_aesthetic_reviews(recommendations, reviews, final_count=2)

    assert [item.id for item in result] == [low_ranker.id, high_ranker.id]
    assert [item.score for item in result] == [0.9, 0.4]


def test_outfit_review_maps_only_used_observations_to_references() -> None:
    recommendation = rank_outfits(
        [
            group("upper_body", [cloth(1, "upper_body", "White", 0.8)]),
            group("lower_body", [cloth(2, "lower_body", "Black", 0.8)]),
        ],
        limit=1,
    )[0]
    observation = OutfitObservation(
        observation_id="obs_used",
        source_url="https://example.com/outfit-guide",
        source_name="Example",
        source_title="正式穿搭指南",
        summary="俐落上衣適合搭配同等正式度的長褲",
        evidence="上下身維持一致正式程度",
        signal_type="timeless",
        confidence=0.9,
    )
    review = AestheticReview(
        occasion_fit=90,
        color_harmony=92,
        silhouette_balance=84,
        material_coherence=82,
        overall_aesthetic=90,
        reason="上下身正式程度一致。",
        knowledge_observation_ids=["obs_used", "obs_not_supplied"],
    )

    result = apply_aesthetic_reviews(
        [recommendation],
        {recommendation.id: review},
        final_count=1,
        observations=[observation],
    )[0]

    assert [reference.model_dump() for reference in result.references] == [
        {"title": "正式穿搭指南", "url": "https://example.com/outfit-guide"}
    ]
