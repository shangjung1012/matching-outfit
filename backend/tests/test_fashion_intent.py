import json

import pytest
from pydantic import ValidationError

from app.models.user_preference import UserHardRule
from app.schemas import (
    FashionIntent,
    OccasionInterpretation,
    RequirementSummary,
    StylingConcept,
)
from app.services.query_planner import (
    FashionIntentInterpreter,
    interpret_fashion_intent_or_none,
)


def make_concept(direction_id: str) -> StylingConcept:
    if direction_id in "ABCDE":
        return StylingConcept(
            direction_id=direction_id,
            concept_name=f"方向 {direction_id}",
            outfit_formula="視覺焦點上衣搭配乾淨俐落下身",
            upper_role="主要視覺焦點",
            lower_role="收斂並平衡上身",
            visible_cues=["清楚腰線", "一個主要設計細節"],
            balance_rules=["只有一件商品承擔最強視覺細節"],
        )
    return StylingConcept(
        direction_id=direction_id,
        concept_name=f"方向 {direction_id}",
        outfit_formula="輪廓清楚的完整連身造型",
        one_piece_role="單一完整視覺焦點",
        visible_cues=["清楚輪廓", "集中式設計細節"],
        balance_rules=["避免互相競爭的圖案"],
    )


def make_fashion_intent(**updates) -> FashionIntent:
    payload = {
        "user_goal": "夏季拍照時呈現鮮明但不像主題扮裝的千禧風格",
        "desired_impression": ["俏皮", "年輕", "上鏡"],
        "occasion_interpretation": OccasionInterpretation(
            social_context="休閒拍照活動",
            formality_target=0.2,
            visual_impact="high",
            practicality="medium",
        ),
        "core_aesthetic": ["高飽和色彩", "千禧風格比例"],
        "must_have_visual_cues": ["強烈色彩存在感", "清楚輪廓"],
        "optional_visual_cues": ["對比滾邊", "金屬感細節"],
        "avoid_concepts": ["成熟花卉造型", "中性極簡基本款"],
        "styling_principles": ["一個主視覺焦點", "支撐單品保持乾淨"],
        "concepts": [make_concept(direction_id) for direction_id in "ABCDEFG"],
        "ambiguities": ["偏好的露膚程度未知"],
        "confidence": 0.86,
    }
    payload.update(updates)
    return FashionIntent.model_validate(payload)


def test_valid_fashion_intent_parses() -> None:
    intent = make_fashion_intent()

    assert [concept.direction_id for concept in intent.concepts] == list("ABCDEFG")
    assert intent.occasion_interpretation.formality_target == 0.2


@pytest.mark.parametrize(
    "concepts",
    [
        [make_concept(direction_id) for direction_id in "ABCDEF"],
        [make_concept(direction_id) for direction_id in "ABCDEFF"],
    ],
)
def test_fashion_intent_rejects_missing_or_duplicate_directions(concepts) -> None:
    with pytest.raises(ValidationError):
        make_fashion_intent(concepts=concepts)


@pytest.mark.parametrize(
    "field,value",
    [("confidence", 1.1), ("formality_target", -0.1)],
)
def test_fashion_intent_rejects_scores_outside_unit_interval(field, value) -> None:
    with pytest.raises(ValidationError):
        if field == "confidence":
            make_fashion_intent(confidence=value)
        else:
            make_fashion_intent(
                occasion_interpretation=OccasionInterpretation(
                    social_context="休閒場合",
                    formality_target=value,
                    visual_impact="medium",
                    practicality="medium",
                )
            )


@pytest.mark.parametrize(
    "direction_index,role_name",
    [(0, "lower_role"), (5, "one_piece_role")],
)
def test_fashion_intent_requires_roles_for_each_direction_kind(
    direction_index: int, role_name: str
) -> None:
    concepts = [make_concept(direction_id) for direction_id in "ABCDEFG"]
    concepts[direction_index] = concepts[direction_index].model_copy(
        update={role_name: None}
    )

    with pytest.raises(ValidationError):
        make_fashion_intent(concepts=concepts)


class FakeIntentLLM:
    def __init__(self, intent: FashionIntent | None = None, error: Exception | None = None):
        self.intent = intent or make_fashion_intent()
        self.error = error
        self.payload = None
        self.stage = None

    def parse(self, *, stage, content, **_):
        self.stage = stage
        self.payload = json.loads(content[0]["text"])
        if self.error:
            raise self.error
        return self.intent


def test_interpreter_preserves_colorful_y2k_meaning_without_floral() -> None:
    llm = FakeIntentLLM()
    intent = FashionIntentInterpreter(llm).interpret(
        raw_user_text="夏天想拍照好看，想要花花綠綠的 Y2K",
        requirement_summary=RequirementSummary(
            seasons=["summer"], styles=["y2k", "colorful"]
        ),
        audience="women",
        hard=None,
        style_preferences=None,
    )

    assert llm.stage == "fashion_intent_interpretation"
    assert llm.payload["raw_user_text"].endswith("Y2K")
    assert "強烈色彩存在感" in intent.must_have_visual_cues
    assert any("花卉" in item for item in intent.avoid_concepts)
    assert any("視覺焦點" in item for item in intent.styling_principles)


def test_interpreter_receives_previous_intent_and_refinement() -> None:
    previous = make_fashion_intent()
    updated = make_fashion_intent(
        occasion_interpretation=OccasionInterpretation(
            social_context="日常穿著",
            formality_target=0.25,
            visual_impact="medium",
            practicality="high",
        )
    )
    llm = FakeIntentLLM(updated)

    result = FashionIntentInterpreter(llm).interpret(
        raw_user_text="想要華麗一點",
        requirement_summary=RequirementSummary(styles=["glamorous"]),
        audience=None,
        hard=None,
        style_preferences=None,
        refinement="不是晚宴華麗，是有設計感但平常能穿",
        previous_intent=previous,
    )

    assert llm.payload["previous_fashion_intent"]["confidence"] == 0.86
    assert "平常能穿" in llm.payload["refinement"]
    assert result.occasion_interpretation.visual_impact == "medium"


def test_interpreter_rejects_strategy_that_conflicts_with_hard_rule() -> None:
    concepts = [make_concept(direction_id) for direction_id in "ABCDEFG"]
    concepts[0] = concepts[0].model_copy(
        update={"upper_role": "black fitted statement top"}
    )
    llm = FakeIntentLLM(make_fashion_intent(concepts=concepts))

    with pytest.raises(RuntimeError, match="hard rules"):
        FashionIntentInterpreter(llm).interpret(
            raw_user_text="不要黑色",
            requirement_summary=RequirementSummary(
                special_requirements=["avoid black"]
            ),
            audience="women",
            hard=UserHardRule(user_key="demo", avoid_colours=["black"]),
            style_preferences=None,
        )


def test_interpreter_timeout_returns_none_for_legacy_planner_fallback() -> None:
    llm = FakeIntentLLM(error=RuntimeError("timeout"))

    intent, fallback_used = interpret_fashion_intent_or_none(
        FashionIntentInterpreter(llm),
        enabled=True,
        raw_user_text="第一次約會但不要太刻意",
        requirement_summary=RequirementSummary(occasions=["first date"]),
        audience=None,
        hard=None,
        style_preferences=None,
    )

    assert intent is None
    assert fallback_used is True


def test_disabled_interpreter_does_not_call_llm() -> None:
    llm = FakeIntentLLM(error=AssertionError("must not be called"))

    intent, fallback_used = interpret_fashion_intent_or_none(
        FashionIntentInterpreter(llm),
        enabled=False,
        raw_user_text="高級餐廳但不要太正式",
        requirement_summary=RequirementSummary(occasions=["fine dining"]),
        audience=None,
        hard=None,
        style_preferences=None,
    )

    assert intent is None
    assert fallback_used is False
    assert llm.payload is None
