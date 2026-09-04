import json

from scripts.import_catalog import (
    load_style_data,
    matches_outfit_demo_profile,
    parse_zone_limits,
    positive_int,
    price_fields,
)


def test_load_style_data_and_use_discounted_price(tmp_path) -> None:
    payload = {
        "data": {
            "id": 10000,
            "price": 649,
            "discountedPrice": 324,
            "brandName": "Palm Tree",
        }
    }
    (tmp_path / "10000.json").write_text(json.dumps(payload), encoding="utf-8")

    style_data = load_style_data(tmp_path, 10000)

    assert style_data is not None
    assert style_data["brandName"] == "Palm Tree"
    assert price_fields(style_data, 1000) == {
        "price": 324,
        "original_price": 649,
        "discounted_price": 324,
    }


def test_price_fields_fall_back_when_json_is_missing() -> None:
    assert price_fields(None, 1000) == {
        "price": 1000,
        "original_price": None,
        "discounted_price": None,
    }


def test_load_style_data_ignores_malformed_json(tmp_path) -> None:
    (tmp_path / "7.json").write_text("not json", encoding="utf-8")

    assert load_style_data(tmp_path, 7) is None
    assert positive_int("649.0") == 649
    assert positive_int(-1) is None


def test_outfit_demo_profile_keeps_adult_outerwear() -> None:
    row = {"articleType": "Shirts", "subCategory": "Topwear"}
    style_data = {"ageGroup": "Adults-Men"}

    assert matches_outfit_demo_profile(row, style_data)


def test_parse_zone_limits() -> None:
    assert parse_zone_limits("upper_body=7000,lower_body=2300,one_piece=700") == {
        "upper_body": 7000,
        "lower_body": 2300,
        "one_piece": 700,
    }


def test_outfit_demo_profile_excludes_socks_innerwear_and_children() -> None:
    assert not matches_outfit_demo_profile(
        {"articleType": "Socks", "subCategory": "Socks"},
        {"ageGroup": "Adults-Unisex"},
    )
    assert not matches_outfit_demo_profile(
        {"articleType": "Briefs", "subCategory": "Innerwear"},
        {"ageGroup": "Adults-Men"},
    )
    assert not matches_outfit_demo_profile(
        {"articleType": "Dresses", "subCategory": "Dress"},
        {"ageGroup": "Kids-Girls"},
    )
