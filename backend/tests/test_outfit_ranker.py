from app.models.user_preference import UserHardRule
from app.models.cloth import Cloth
from app.schemas import (
    ClothResult,
    QueryDraft,
    QuerySearchResult,
    ReferenceLink,
    RequirementSummary,
    StylePreferenceProposalRequest,
)
from app.api.routes import effective_audience, outfit_memory_proposals
from app.services.outfit_ranker import rank_outfits, select_diverse


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
    zone: str, clothes: list[ClothResult], references: list[ReferenceLink] | None = None
) -> QuerySearchResult:
    return QuerySearchResult(
        query=QueryDraft(
            id=zone,
            text=zone,
            garment_zone=zone,
            rationale="test",
            references=references or [],
        ),
        clothes=[
            item.model_copy(update={"references": references or []}) for item in clothes
        ],
    )


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


def test_ranker_includes_accessory_when_formula_requested_one() -> None:
    groups = [
        group("upper_body", [cloth(1, "upper_body", "White", 0.9)]),
        group("lower_body", [cloth(2, "lower_body", "Beige", 0.9)]),
        group("accessory", [cloth(3, "accessory", "Brown", 0.85)]),
    ]

    recommendations = rank_outfits(groups, limit=1)

    assert len(recommendations[0].items) == 3
    assert recommendations[0].items[-1].garment_zone == "accessory"


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
