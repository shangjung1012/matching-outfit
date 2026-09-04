from app.schemas.styling import OutfitObservation
from app.knowledge.ingestion.db_importer import (
    observation_audiences,
    observation_embedding_text,
)
from app.knowledge.retrieval import (
    infer_audience,
)


def make_observation(**overrides) -> OutfitObservation:
    values = {
        "summary": "黑色修身長裙適合正式晚宴",
        "evidence": "以俐落剪裁維持正式感",
        "audiences": [],
        "occasions": ["正式晚宴"],
        "climates": [],
        "seasons": [],
        "styles": ["優雅"],
        "garments": ["長裙"],
        "colors": ["黑色"],
        "materials": [],
        "silhouettes": ["修身"],
        "styling_actions": [],
        "avoid_when": ["海灘活動"],
        "signal_type": "timeless",
        "confidence": 0.9,
    }
    values.update(overrides)
    return OutfitObservation(**values)


def test_existing_source_supplies_gender_audience() -> None:
    observation = make_observation()

    assert observation_audiences(observation, "elle.com") == ["women"]
    assert observation_audiences(observation, "gqkorea.co.kr") == ["men"]
    assert observation_audiences(observation, "unknown.example") == ["unisex"]


def test_explicit_audience_is_preserved() -> None:
    observation = make_observation(audiences=["unisex"])

    assert observation_audiences(observation, "elle.com") == ["unisex"]


def test_embedding_text_contains_retrieval_fields() -> None:
    text = observation_embedding_text(make_observation(), ["women"])

    assert "audiences: women" in text
    assert "正式晚宴" in text
    assert "海灘活動" in text


def test_audience_can_be_explicit_or_inferred() -> None:
    assert infer_audience("幫男生搭配上班服裝") == "men"
    assert infer_audience("women formal dinner outfit") == "women"
    assert infer_audience("日常逛街") is None
    assert infer_audience("日常逛街", "unisex") == "unisex"
