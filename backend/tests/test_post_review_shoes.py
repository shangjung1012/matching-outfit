from app.schemas import AestheticReview, RequirementSummary, ShoeSpec
from app.services import post_review_shoes
from tests.test_recommendation_debug import _outfit, _query


def test_post_review_shoe_is_appended_without_changing_outfit_score(monkeypatch) -> None:
    outfit = _outfit(_query()).model_copy(update={
        "score": 0.82,
        "aesthetic_review": AestheticReview(
            occasion_fit=80,
            color_harmony=80,
            silhouette_balance=80,
            material_coherence=80,
            overall_aesthetic=80,
            reason="coherent clothing outfit",
            shoe_spec=ShoeSpec(
                shoe_type="loafer",
                shoe_color="black",
                shoe_query="black leather loafers clean low profile",
            ),
        ),
        "items": [_outfit(_query()).items[0].model_copy(update={"base_colour": "Black"})],
    })
    shoe = outfit.items[0].model_copy(update={
        "id": 999,
        "product_display_name": "Black loafers",
        "garment_zone": "accessory",
        "similarity": 0.73,
    })
    received = []

    def fake_search(_db, specs, **kwargs):
        received.extend(specs)
        assert kwargs == {"audience": "women", "hard": None, "top_k": 5}
        return [[shoe]]

    monkeypatch.setattr(post_review_shoes, "search_shoe_candidates", fake_search)
    result = post_review_shoes.attach_post_review_shoes(
        object(), [outfit], {outfit.id: ShoeSpec(shoe_type="loafer", shoe_query="black leather loafers clean low profile")}, audience="women", hard=None
    )

    assert received[0].shoe_query == "black leather loafers clean low profile"
    assert result[0].score == 0.82
    assert [item.id for item in result[0].items] == [item.id for item in outfit.items] + [999]
    assert result[0].shoe_suggestion is not None
    assert result[0].shoe_suggestion.item_id == 999
    assert result[0].shoe_suggestion.retrieval_score == 0.73


def test_missing_shoe_result_leaves_outfit_unchanged(monkeypatch) -> None:
    outfit = _outfit(_query()).model_copy(update={
        "aesthetic_review": AestheticReview(
            occasion_fit=80,
            color_harmony=80,
            silhouette_balance=80,
            material_coherence=80,
            overall_aesthetic=80,
            reason="coherent clothing outfit",
            shoe_spec=ShoeSpec(shoe_query="white low profile sneakers"),
        ),
    })
    monkeypatch.setattr(post_review_shoes, "search_shoe_candidates", lambda *_args, **_kwargs: [[]])

    result = post_review_shoes.attach_post_review_shoes(
        object(), [outfit], {outfit.id: ShoeSpec(shoe_type="sneaker", shoe_query="white low profile sneakers")}, audience=None, hard=None
    )

    assert result == [outfit]


def test_shoe_debug_keeps_query_and_top_candidates(monkeypatch) -> None:
    outfit = _outfit(_query())
    first = outfit.items[0].model_copy(update={"id": 901, "similarity": 0.91})
    second = outfit.items[0].model_copy(update={"id": 902, "similarity": 0.84})
    monkeypatch.setattr(
        post_review_shoes,
        "search_shoe_candidates",
        lambda *_args, **_kwargs: [[first, second]],
    )

    result, traces = post_review_shoes.attach_post_review_shoes(
        object(),
        [outfit],
        {outfit.id: ShoeSpec(shoe_type="loafer", shoe_query="black leather loafers")},
        audience=None,
        hard=None,
        include_debug=True,
    )

    assert result[0].shoe_suggestion is not None
    assert traces[0].original_query == "black leather loafers"
    assert traces[0].query == "black leather loafers"
    assert [item.id for item in traces[0].candidates] == [901, 902]
    assert traces[0].selected_item_id == 901


def test_conservative_shoe_colour_follows_formality_and_lower_outfit_colours() -> None:
    outfit = _outfit(_query())
    outfit.items = [
        outfit.items[0].model_copy(update={"base_colour": "Black"}),
        outfit.items[0].model_copy(update={"id": 2, "garment_zone": "lower_body", "base_colour": "Beige"}),
    ]
    assert post_review_shoes.choose_shoe_color(
        outfit, RequirementSummary(formalities=["formal"]), "interview outfit"
    ) == "dark brown"

    outfit.items[0] = outfit.items[0].model_copy(update={"base_colour": "Red"})
    outfit.items[1] = outfit.items[1].model_copy(update={"base_colour": "Black"})
    assert post_review_shoes.choose_shoe_color(outfit, None, "casual dinner") == "black"
