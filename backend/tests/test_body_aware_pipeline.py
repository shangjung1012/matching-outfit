"""Offline contract regressions; real-model semantic quality requires separate evals."""
import json
from collections import Counter

import pytest

from app.schemas.workflow import BodyContext, BodyStrategy, RequirementSummary
from app.services import aesthetic_reviewer as reviewer_module
from app.services.aesthetic_reviewer import AestheticReviewer, AestheticReviewBatch, CandidateAestheticReview
from app.services.query_planner import (
    FashionIntentInterpreter, QueryPlanner, FASHION_INTENT_INTERPRETER_PROMPT,
    QUERY_PLANNER_SYSTEM_PROMPT,
)
from tests.test_fashion_intent import FakeIntentLLM, make_fashion_intent
from tests.test_query_planner import FakeLLM, query_rows
from tests.test_recommendation_debug import _outfit, _query


CASES = [
    ("A", "BMI較高，週末去咖啡廳", {"bmi_band": "higher"},
     {"soft_biases": ["部分方向偏好適中鬆量，保留合身與短版"]}),
    ("B", "BMI較高，我喜歡短版合身上衣", {"bmi_band": "higher", "fit_preference": "fitted"},
     {"fit_direction": ["合身不等於緊繃"], "proportion_direction": ["短版上衣"]}),
    ("C", "我比較矮，喜歡寬褲", {"height_band": "short"},
     {"proportion_direction": ["可紮上衣與適中寬褲"]}),
    ("D", "腿長軀幹短，想平衡比例", {"leg_torso_ratio": "longer_legs"},
     {"proportion_direction": ["部分方向中腰與稍長上衣"]}),
    ("E", "上下都想寬鬆，但比例要清楚", {"fit_preference": "relaxed"},
     {"proportion_direction": ["長短差與受控垂墜"]}),
    ("F", "需要單手穿脫，避免小扣子", {"access_needs": ["單手穿脫", "避免小扣子"]},
     {"movement_and_access_direction": ["可觀察的鬆緊腰與套穿結構"],
      "hard_constraints": ["避免小扣子"]}),
    ("G", "週末去咖啡廳", {}, {}),
]


@pytest.mark.parametrize("case,user_text,context,strategy", CASES, ids=list("ABCDEFG"))
def test_body_contract_survives_interpret_plan_review(monkeypatch, case, user_text, context, strategy):
    accepted = make_fashion_intent(
        body_context=BodyContext(**context),
        body_strategy=BodyStrategy(**strategy),
    )
    interpreter_llm = FakeIntentLLM(accepted)
    intent = FashionIntentInterpreter(interpreter_llm).interpret(
        raw_user_text=user_text, requirement_summary=RequirementSummary(),
        audience=None, hard=None, style_preferences=[],
    )

    class PlannerLLM(FakeLLM):
        def parse(self, **kwargs):
            draft = super().parse(**kwargs)
            rows = query_rows()
            tops = [
                "fitted cropped knit top", "regular full length shirt",
                "tuckable softly structured blouse", "relaxed cropped boxy top",
                "regular long sleeve top",
            ]
            bottoms = [
                "mid rise straight leg trousers", "high waist relaxed trousers",
                "moderate wide leg trousers", "fluid midi skirt",
                "elastic waist pull on trousers",
            ]
            for row, text in zip(rows[:5], tops):
                row.text = text
            for row, text in zip(rows[5:10], bottoms):
                row.text = text
            for row in rows[10:]:
                row.text = "regular waist defined midi dress"
            return draft.model_copy(update={"queries": rows})

    planner_llm = PlannerLLM()
    plan = QueryPlanner(planner_llm).plan(user_text, fashion_intent=intent)
    assert planner_llm.payloads[0]["fashion_intent"]["body_strategy"] == intent.body_strategy.model_dump()
    assert Counter(q.garment_zone for q in plan.queries) == {
        "upper_body": 5, "lower_body": 5, "one_piece": 2,
    }
    assert Counter(q.direction_id for q in plan.queries) == Counter("AABBCCDDEEFG")
    assert all(len(q.text.split()) <= 22 for q in plan.queries)
    assert any("fitted" in q.text for q in plan.queries)
    assert any("wide leg" in q.text for q in plan.queries)
    assert any("mid rise" in q.text for q in plan.queries)
    assert not any("dark" in q.text for q in plan.queries)
    assert intent.body_context.shoulder_hip_balance == "unknown"
    assert intent.body_context.midsection_fullness == "unknown"
    if case == "G":
        assert not intent.body_strategy.hard_constraints
    if case == "A":
        assert intent.body_strategy.confidence == "low"

    class ReviewLLM:
        def parse(self, *, content, instructions, **_):
            payload = json.loads(content[0]["text"])
            assert payload["body_strategy"] == intent.body_strategy.model_dump()
            assert payload["body_context"] == intent.body_context.model_dump()
            assert "Do not infer the user's body from the catalog model." in instructions
            return AestheticReviewBatch(reviews=[CandidateAestheticReview(
                candidate_id=payload["candidates"][0]["candidate_id"],
                occasion_fit=75, color_harmony=75, silhouette_balance=75,
                material_coherence=75, overall_aesthetic=75,
                reason="比例協調；操作力道無法由圖片確認。",
            )])

    monkeypatch.setattr(reviewer_module, "outfit_contact_sheet_data_url", lambda _: "data:image/jpeg;base64,test")
    AestheticReviewer(ReviewLLM()).review(user_text, [_outfit(_query())], fashion_intent=intent)


def test_shared_safety_and_role_specific_rules_are_loaded():
    for prompt in (
        FASHION_INTENT_INTERPRETER_PROMPT, QUERY_PLANNER_SYSTEM_PROMPT,
        reviewer_module.AESTHETIC_REVIEW_PROMPT,
    ):
        assert "Unknown means unknown." in prompt
        assert '"Fitted" does not mean skin-tight.' in prompt
        assert "Do not describe body characteristics as flaws." in prompt
    assert "keep fitted and cropped options available" in FASHION_INTENT_INTERPRETER_PROMPT
    assert "authoritative body-aware translation" in QUERY_PLANNER_SYSTEM_PROMPT
    assert "Low-confidence BMI biases must never be fatal_issues" in reviewer_module.AESTHETIC_REVIEW_PROMPT


def test_old_intents_default_to_unknown_without_new_constraints():
    intent = make_fashion_intent()
    assert intent.body_context == BodyContext()
    assert intent.body_strategy == BodyStrategy()
