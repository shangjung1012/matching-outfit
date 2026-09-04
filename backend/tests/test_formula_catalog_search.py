import pytest

from app.schemas.styling import GarmentSearchSpec, OutfitFormula
from app.services.formula_catalog_search import formula_queries


def formula(specs: list[GarmentSearchSpec]) -> OutfitFormula:
    return OutfitFormula(
        name="清爽海邊搭配",
        items=["亞麻襯衫", "寬褲"],
        palette=["white", "beige"],
        silhouette="上身放鬆、下身垂直",
        why_it_works="中性色和透氣外觀保持清爽",
        context_fit="適合炎熱休閒環境",
        search_specs=specs,
    )


def spec(zone: str, query: str) -> GarmentSearchSpec:
    return GarmentSearchSpec(garment_zone=zone, query=query, rationale="測試搜尋")


def test_formula_queries_create_zone_specific_fashion_clip_queries() -> None:
    queries = formula_queries(
        formula(
            [
                spec("upper_body", "white relaxed linen shirt"),
                spec("lower_body", "beige wide leg lightweight trousers"),
                spec("accessory", "minimal tan flat sandals"),
            ]
        )
    )

    assert [query.garment_zone for query in queries] == [
        "upper_body",
        "lower_body",
        "accessory",
    ]
    assert queries[0].text == "white relaxed linen shirt"


def test_formula_queries_reject_mixed_one_piece_and_separates() -> None:
    invalid = formula(
        [
            spec("upper_body", "white blouse"),
            spec("lower_body", "black trousers"),
            spec("one_piece", "black midi dress"),
        ]
    )

    with pytest.raises(ValueError, match=r"upper\+lower or one_piece"):
        formula_queries(invalid)
