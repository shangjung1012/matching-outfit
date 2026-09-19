from app.models.user_preference import UserHardRule
from app.models.cloth import Cloth
from app.schemas import (
    AestheticReview,
    ClothResult,
    FashionIntent,
    QueryDraft,
    QuerySearchResult,
    ReferenceLink,
    RequirementSummary,
    StylePreferenceProposalRequest,
)
from app.api.routes import effective_audience, outfit_memory_proposals
from app.services.outfit_ranker import (
    _color_pair_score,
    _fashion_intent_requests_bold_color,
    fashion_intent_color_mode,
    parse_color,
    rank_outfits,
    select_diverse,
)


def cloth(identifier: int, zone: str, color: str, similarity: float) -> ClothResult:
    return ClothResult(
        id=identifier,
        source_item_id=identifier,
        product_display_name=f"item-{identifier}",
        garment_zone=zone,
        image_url=f"/media/{identifier}.jpg",
        price=1000,
        base_colour=color,
        article_type="Tshirts" if zone == "upper_body" else "Trousers",
        similarity=similarity,
    )


def group(
    zone: str,
    clothes: list[ClothResult],
    references: list[ReferenceLink] | None = None,
    direction_id: str | None = None,
) -> QuerySearchResult:
    return QuerySearchResult(
        query=QueryDraft(
            id=zone,
            text=zone,
            garment_zone=zone,
            rationale="test",
            direction_id=direction_id,
            references=references or [],
        ),
        clothes=[
            item.model_copy(update={"references": references or []}) for item in clothes
        ],
    )


def test_parse_color_preserves_lightness_and_base_family() -> None:
    assert parse_color("Light Blue") == ("light", "blue")
    assert parse_color("Dark Green") == ("dark", "green")
    assert parse_color("Blue") == ("normal", "blue")
    assert parse_color("Navy Blue") == ("normal", "navy")
    assert parse_color("Other Blue") == ("normal", "blue")
    assert parse_color("Off White") == ("normal", "cream")


def test_color_pair_score_understands_tones_and_color_families() -> None:
    assert _color_pair_score("Light Blue", "Light Blue") == 0.86
    assert _color_pair_score("Light Blue", "Dark Blue") == 0.90
    assert _color_pair_score("Light Beige", "Blue") == 0.80
    assert _color_pair_score("Black", "White") == 0.95
    assert _color_pair_score("Beige", "Brown") == 0.95
    assert _color_pair_score("Navy Blue", "Cream") == 0.95
    assert _color_pair_score("Beige", "Purple") == 0.80
    assert _color_pair_score("Black", "Orange") == 0.80
    assert _color_pair_score("Orange", "Green") == 0.35
    assert _color_pair_score("Light Orange", "Green") == 0.65
    assert _color_pair_score("Light Orange", "Light Green") == 0.70


def test_explicit_bold_fashion_intent_overrides_default_clash_penalty() -> None:
    intent = FashionIntent.model_construct(
        desired_impression=["playful"],
        core_aesthetic=["colorful Y2K"],
        must_have_visual_cues=["deliberate high-saturation color blocking"],
        optional_visual_cues=[],
        styling_principles=[],
    )

    color_mode = fashion_intent_color_mode(intent)

    assert _fashion_intent_requests_bold_color(intent) is True
    assert color_mode == "contrast"
    assert _color_pair_score("Red", "Green", color_mode=color_mode) == 0.86


def test_vivid_intent_softens_but_does_not_erase_clash_penalty() -> None:
    intent = FashionIntent.model_construct(
        desired_impression=["vivid and colorful"],
        core_aesthetic=["playful color"],
        must_have_visual_cues=["high-saturation garment"],
        optional_visual_cues=[],
        styling_principles=[],
    )

    color_mode = fashion_intent_color_mode(intent)

    assert color_mode == "vivid"
    assert _color_pair_score("Red", "Green", color_mode=color_mode) == 0.65


def test_ranker_only_combines_upper_and_lower_from_same_styling_direction() -> None:
    recommendations = rank_outfits(
        [
            group(
                "upper_body",
                [cloth(101, "upper_body", "Pink", 0.9)],
                direction_id="A",
            ),
            group(
                "lower_body",
                [cloth(102, "lower_body", "Blue", 0.9)],
                direction_id="A",
            ),
            group(
                "upper_body",
                [cloth(103, "upper_body", "Black", 0.9)],
                direction_id="B",
            ),
            group(
                "lower_body",
                [cloth(104, "lower_body", "White", 0.9)],
                direction_id="B",
            ),
        ],
        limit=10,
    )

    combinations = {
        tuple(item.id for item in recommendation.items)
        for recommendation in recommendations
    }
    assert combinations == {(101, 102), (103, 104)}
    assert {item.direction_id for item in recommendations} == {"A", "B"}


def test_ranker_applies_budget_after_combining_items() -> None:
    upper = cloth(501, "upper_body", "White", 0.95).model_copy(update={"price": 1500})
    lower = cloth(502, "lower_body", "Black", 0.95).model_copy(update={"price": 600})
    one_piece = cloth(503, "one_piece", "Navy", 0.80).model_copy(update={"price": 1800})

    recommendations = rank_outfits(
        [
            group("upper_body", [upper], direction_id="A"),
            group("lower_body", [lower], direction_id="A"),
            group("one_piece", [one_piece]),
        ],
        outfit_budget_max=2000,
    )

    assert [[item.id for item in outfit.items] for outfit in recommendations] == [[503]]


def test_ranker_preserves_best_one_piece_direction() -> None:
    dress = cloth(504, "one_piece", "Pink", 0.91).model_copy(
        update={"article_type": "Dresses"}
    )

    recommendations = rank_outfits(
        [
            group("one_piece", [dress.model_copy(update={"similarity": 0.72})], direction_id="A"),
            group("one_piece", [dress], direction_id="C"),
        ],
        limit=1,
    )

    assert recommendations[0].direction_id == "C"


def test_ranker_preserves_candidates_from_each_styling_direction() -> None:
    recommendations = rank_outfits(
        [
            group(
                "upper_body",
                [cloth(201, "upper_body", "White", 0.90), cloth(202, "upper_body", "White", 0.89)],
                direction_id="A",
            ),
            group(
                "lower_body",
                [cloth(203, "lower_body", "Black", 0.90), cloth(204, "lower_body", "Black", 0.89)],
                direction_id="A",
            ),
            group(
                "upper_body",
                [cloth(205, "upper_body", "Beige", 0.86)],
                direction_id="B",
            ),
            group(
                "lower_body",
                [cloth(206, "lower_body", "Brown", 0.86)],
                direction_id="B",
            ),
        ],
        limit=2,
    )

    assert {item.direction_id for item in recommendations} == {"A", "B"}


def test_liked_outfit_creates_one_context_scoped_preference_sentence() -> None:
    upper = Cloth(id=70, product_display_name="Silk Shirt")
    lower = Cloth(id=71, product_display_name="Wide Leg Trousers")
    payload = StylePreferenceProposalRequest(
        user_key="demo",
        user_request="秋天參加戶外婚禮，希望正式但方便走動",
        outfit_item_ids=[[70, 71]],
        requirements=RequirementSummary(
            occasions=["outdoor wedding"],
            seasons=["autumn"],
            times_of_day=["evening"],
            climates=["outdoor"],
            formalities=["formal"],
            activities=["walking on grass"],
        ),
    )

    proposals = outfit_memory_proposals({70: upper, 71: lower}, payload)

    assert len(proposals) == 1
    assert "秋天參加戶外婚禮" in proposals[0].preference_text
    assert "Silk Shirt、Wide Leg Trousers" in proposals[0].preference_text
    assert proposals[0].occasions == ["outdoor wedding"]


def test_explicit_request_overrides_profile_gender_audience() -> None:
    profile = UserHardRule(user_key="demo", gender="female")

    assert effective_audience("想找男裝西裝", None, profile) == "men"
    assert effective_audience("想找正式西裝", None, profile) == "women"
    assert effective_audience("想找正式西裝", "unisex", profile) == "unisex"


def test_ranker_does_not_attach_query_stage_references() -> None:
    recommendations = rank_outfits(
        [
            group(
                "upper_body",
                [cloth(50, "upper_body", "White", 0.9)],
                [ReferenceLink(title="舊 Query 來源", url="https://example.com/old")],
            ),
            group(
                "lower_body",
                [cloth(51, "lower_body", "Black", 0.9)],
            ),
        ],
        limit=1,
    )

    assert recommendations[0].references == []


def test_ranker_ignores_accessory_query_results() -> None:
    groups = [
        group("upper_body", [cloth(1, "upper_body", "White", 0.9)]),
        group("lower_body", [cloth(2, "lower_body", "Beige", 0.9)]),
        group("accessory", [cloth(3, "accessory", "Brown", 0.85)]),
    ]

    recommendations = rank_outfits(groups, limit=1)

    assert [item.garment_zone for item in recommendations[0].items] == [
        "upper_body",
        "lower_body",
    ]


def test_ranker_penalizes_casual_items_in_strict_formal_context() -> None:
    formal_upper = cloth(1, "upper_body", "White", 0.8).model_copy(
        update={"article_type": "Shirts", "usage": "Formal"}
    )
    casual_upper = cloth(2, "upper_body", "White", 0.8).model_copy(
        update={"article_type": "Tshirts", "usage": "Casual"}
    )
    lower = cloth(3, "lower_body", "Black", 0.8).model_copy(
        update={"article_type": "Trousers", "usage": "Formal"}
    )

    recommendations = rank_outfits(
        [group("upper_body", [casual_upper, formal_upper]), group("lower_body", [lower])],
        user_context="去高級餐廳吃正式晚餐",
    )

    assert recommendations[0].items[0].id == formal_upper.id
    assert recommendations[0].score_breakdown is not None
    assert recommendations[0].score_breakdown.context_fit > recommendations[1].score_breakdown.context_fit


def test_select_diverse_avoids_reusing_same_garment_when_possible() -> None:
    upper = cloth(1, "upper_body", "White", 0.9)
    first = rank_outfits(
        [group("upper_body", [upper]), group("lower_body", [cloth(2, "lower_body", "Black", 0.9)])]
    )[0]
    repeated = rank_outfits(
        [group("upper_body", [upper]), group("lower_body", [cloth(3, "lower_body", "Navy", 0.88)])]
    )[0]
    distinct = rank_outfits(
        [
            group("upper_body", [cloth(4, "upper_body", "Cream", 0.86)]),
            group("lower_body", [cloth(5, "lower_body", "Brown", 0.86)]),
        ]
    )[0]

    selected = select_diverse([first, repeated, distinct], 2)

    assert selected == [first, distinct]


def test_select_diverse_avoids_repeating_same_color_and_garment_profile() -> None:
    white_set_one = rank_outfits(
        [
            group("upper_body", [cloth(10, "upper_body", "White", 0.95)]),
            group("lower_body", [cloth(11, "lower_body", "White", 0.95)]),
        ]
    )[0]
    white_set_two = rank_outfits(
        [
            group("upper_body", [cloth(12, "upper_body", "White", 0.94)]),
            group("lower_body", [cloth(13, "lower_body", "White", 0.94)]),
        ]
    )[0]
    colorful_set = rank_outfits(
        [
            group("upper_body", [cloth(14, "upper_body", "Pink", 0.90)]),
            group("lower_body", [cloth(15, "lower_body", "Blue", 0.90)]),
        ]
    )[0]

    selected = select_diverse([white_set_one, white_set_two, colorful_set], 2)

    assert selected == [white_set_one, colorful_set]


def test_select_diverse_keeps_one_piece_option_when_available() -> None:
    separates = rank_outfits(
        [
            group("upper_body", [cloth(20, "upper_body", "Yellow", 0.95)]),
            group("lower_body", [cloth(21, "lower_body", "White", 0.95)]),
        ]
    )[0]
    second_separates = rank_outfits(
        [
            group("upper_body", [cloth(22, "upper_body", "Pink", 0.94)]),
            group("lower_body", [cloth(23, "lower_body", "Blue", 0.94)]),
        ]
    )[0]
    dress = rank_outfits(
        [group("one_piece", [cloth(24, "one_piece", "Multi", 0.85)])]
    )[0]

    selected = select_diverse([separates, second_separates, dress], 2)

    assert [recommendation.kind for recommendation in selected] == ["separates", "one_piece"]


def test_ranked_pool_reserves_space_for_both_outfit_kinds() -> None:
    recommendations = rank_outfits(
        [
            group(
                "upper_body",
                [
                    cloth(30, "upper_body", "Yellow", 0.95),
                    cloth(31, "upper_body", "Pink", 0.94),
                ],
            ),
            group(
                "lower_body",
                [
                    cloth(32, "lower_body", "White", 0.95),
                    cloth(33, "lower_body", "Blue", 0.94),
                ],
            ),
            group(
                "one_piece",
                [
                    cloth(34, "one_piece", "Multi", 0.85),
                    cloth(35, "one_piece", "Green", 0.84),
                ],
            ),
        ],
        limit=4,
    )

    assert sum(item.kind == "separates" for item in recommendations) == 2
    assert sum(item.kind == "one_piece" for item in recommendations) == 2


def test_select_diverse_does_not_force_unsuitable_outfit_kind() -> None:
    first = rank_outfits(
        [
            group("upper_body", [cloth(40, "upper_body", "Yellow", 0.95)]),
            group("lower_body", [cloth(41, "lower_body", "White", 0.95)]),
        ]
    )[0]
    second = rank_outfits(
        [
            group("upper_body", [cloth(42, "upper_body", "Pink", 0.93)]),
            group("lower_body", [cloth(43, "lower_body", "Blue", 0.93)]),
        ]
    )[0]
    unsuitable_dress = rank_outfits(
        [group("one_piece", [cloth(44, "one_piece", "Multi", 0.40)])]
    )[0].model_copy(update={"score": 0.30})

    selected = select_diverse([first, second, unsuitable_dress], 2)

    assert [recommendation.kind for recommendation in selected] == ["separates", "separates"]


def test_select_diverse_prefers_quality_close_bottom_color_variety() -> None:
    upper_colors = ["Blue", "Light Blue", "Dark Blue", "White", "Pink"]
    black_bottoms = [
        rank_outfits(
            [
                group("upper_body", [cloth(100 + index, "upper_body", color, 0.90)]),
                group("lower_body", [cloth(200 + index, "lower_body", "Black", 0.90)]),
            ]
        )[0].model_copy(update={"score": 0.90 - index * 0.01})
        for index, color in enumerate(upper_colors)
    ]
    white_bottom = rank_outfits(
        [
            group("upper_body", [cloth(300, "upper_body", "Blue", 0.90)]),
            group("lower_body", [cloth(301, "lower_body", "White", 0.90)]),
        ]
    )[0].model_copy(update={"score": 0.84})

    selected = select_diverse([*black_bottoms, white_bottom], 5)

    assert sum(
        item.base_colour == "Black"
        for recommendation in selected
        for item in recommendation.items
        if item.garment_zone == "lower_body"
    ) == 4
    assert white_bottom in selected


def test_select_diverse_does_not_trade_quality_for_bottom_color_variety() -> None:
    black_bottoms = [
        rank_outfits(
            [
                group("upper_body", [cloth(400 + index, "upper_body", color, 0.90)]),
                group("lower_body", [cloth(500 + index, "lower_body", "Black", 0.90)]),
            ]
        )[0].model_copy(update={"score": 0.90 - index * 0.01})
        for index, color in enumerate(["Blue", "Light Blue", "Dark Blue", "White", "Pink"])
    ]
    low_quality_white = rank_outfits(
        [
            group("upper_body", [cloth(600, "upper_body", "Blue", 0.70)]),
            group("lower_body", [cloth(601, "lower_body", "White", 0.70)]),
        ]
    )[0].model_copy(update={"score": 0.70})

    selected = select_diverse([*black_bottoms, low_quality_white], 5)

    assert selected == black_bottoms


def test_select_diverse_never_uses_fatal_candidate_to_fill_limit() -> None:
    good = rank_outfits(
        [
            group("upper_body", [cloth(700, "upper_body", "Blue", 0.90)]),
            group("lower_body", [cloth(701, "lower_body", "Black", 0.90)]),
        ]
    )[0]
    fatal = rank_outfits(
        [
            group("upper_body", [cloth(702, "upper_body", "Pink", 0.89)]),
            group("lower_body", [cloth(703, "lower_body", "White", 0.89)]),
        ]
    )[0].model_copy(
        update={
            "aesthetic_review": AestheticReview(
                occasion_fit=80,
                color_harmony=20,
                silhouette_balance=80,
                material_coherence=80,
                overall_aesthetic=40,
                fatal_issues=["prohibited color"],
                reason="Visible hard-constraint violation",
            )
        }
    )

    assert select_diverse([good, fatal], 2) == [good]


def test_select_diverse_does_not_fill_results_with_low_reviewed_quality() -> None:
    good = rank_outfits(
        [
            group("upper_body", [cloth(800, "upper_body", "Blue", 0.90)]),
            group("lower_body", [cloth(801, "lower_body", "White", 0.90)]),
        ]
    )[0]
    unattractive = rank_outfits(
        [
            group("upper_body", [cloth(802, "upper_body", "Orange", 0.88)]),
            group("lower_body", [cloth(803, "lower_body", "Orange", 0.88)]),
        ]
    )[0].model_copy(
        update={
            "score": 0.55,
            "aesthetic_review": AestheticReview(
                occasion_fit=50,
                color_harmony=60,
                silhouette_balance=55,
                material_coherence=55,
                overall_aesthetic=55,
                reason="Visible athletic styling misses the polished vacation identity",
            ),
        }
    )

    assert select_diverse([good, unattractive], 2) == [good]
