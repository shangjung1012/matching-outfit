from app.api import routes
from app.schemas import (
    ClothResult,
    OutfitRecommendation,
    OutfitScoreBreakdown,
    QueryDraft,
    QuerySearchResult,
    SearchRequest,
)


def _query() -> QueryDraft:
    return QueryDraft(
        id="query-a",
        text="bright fitted cropped baby tee",
        garment_zone="upper_body",
        rationale="鮮明短版上衣",
        direction_id="A",
    )


def _outfit(query: QueryDraft) -> OutfitRecommendation:
    item = ClothResult(
        id=1,
        source_item_id=1001,
        product_display_name="Cropped tee",
        garment_zone="upper_body",
        image_url="/media/1001.jpg",
        price=499,
        currency="TWD",
        base_colour="Bright Pink",
        article_type="Tops",
        similarity=0.81,
    )
    return OutfitRecommendation(
        id="outfit-a",
        kind="separates",
        items=[item],
        score=0.75,
        reasons=["test candidate"],
        score_breakdown=OutfitScoreBreakdown(
            fashion_clip=0.81,
            compatibility=0.72,
            context_fit=0.75,
        ),
    )


def test_recommendation_debug_contains_retrieval_and_ranker_stages(monkeypatch) -> None:
    query = _query()
    group = QuerySearchResult(query=query, clothes=_outfit(query).items)
    outfit = _outfit(query)
    monkeypatch.setattr(routes, "hard_rules_for", lambda *_: None)
    monkeypatch.setattr(routes, "search_catalog", lambda *_args, **_kwargs: [group])
    monkeypatch.setattr(routes, "rank_outfits", lambda *_args, **_kwargs: [outfit])
    monkeypatch.setattr(
        routes, "select_diverse", lambda recommendations, limit: recommendations[:limit]
    )
    monkeypatch.setattr(routes.settings, "aesthetic_review_enabled", False)

    response = routes.recommendations(
        SearchRequest(
            queries=[query],
            user_input="夏天拍照",
            include_debug=True,
        ),
        db=object(),
    )

    assert response.debug is not None
    assert response.debug.search_results[0].query.text == query.text
    assert response.debug.ranked_candidate_count == 1
    assert response.debug.ranked_preview[0].id == outfit.id
    assert response.debug.shortlist_before_review[0].score == outfit.score
    assert response.debug.aesthetic_review_attempted is False


def test_recommendation_debug_is_additive_and_off_by_default(monkeypatch) -> None:
    query = _query()
    outfit = _outfit(query)
    monkeypatch.setattr(routes, "hard_rules_for", lambda *_: None)
    monkeypatch.setattr(routes, "search_catalog", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(routes, "rank_outfits", lambda *_args, **_kwargs: [outfit])
    monkeypatch.setattr(
        routes, "select_diverse", lambda recommendations, limit: recommendations[:limit]
    )
    monkeypatch.setattr(routes.settings, "aesthetic_review_enabled", False)

    response = routes.recommendations(
        SearchRequest(queries=[query], user_input="夏天拍照"),
        db=object(),
    )

    assert response.debug is None
