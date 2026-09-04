import json

import pytest

from app.schemas.workflow import ActivityContext, RequirementSummary
from app.services import aesthetic_reviewer as module
from app.services.aesthetic_reviewer import (
    AestheticReviewer, AestheticReviewBatch, CandidateAestheticReview, apply_aesthetic_reviews,
)
from app.services.query_planner import FashionIntentInterpreter, QueryPlanner
from tests.test_fashion_intent import FakeIntentLLM, make_fashion_intent
from tests.test_query_planner import FakeLLM
from tests.test_recommendation_debug import _outfit, _query


@pytest.mark.parametrize("appearance,function,activity,mode", [
    ("high", "low", True, "appearance_dominant"),
    ("medium", "high", True, "function_dominant"),
    ("high", "high", True, "balanced"),
    ("high", "medium", True, "appearance_dominant"),
    ("low", "low", False, "not_applicable"),
])
def test_independent_activity_priorities(appearance, function, activity, mode):
    result = ActivityContext(
        activity_present=activity, appearance_priority=appearance,
        functional_priority=function, activity_mode="balanced",
    )
    assert result.activity_mode == mode
    assert result.appearance_priority == appearance
    assert result.functional_priority == function


def test_new_priorities_override_legacy_mode():
    result = ActivityContext(
        activity_mode="functional_training", appearance_priority="high",
        functional_priority="low",
    )
    assert result.activity_mode == "appearance_dominant"


def test_review_schema_requires_new_dimensions():
    required = CandidateAestheticReview.model_json_schema()["required"]
    assert set([
        "style_identity_match", "silhouette_proportion", "pairing_coherence",
        "color_material_harmony", "constraint_compliance",
        "style_drift_detected", "style_drift_evidence",
    ]).issubset(required)


def test_minor_sporty_elements_do_not_cap_or_reject(monkeypatch):
    monkeypatch.setattr(module, "outfit_contact_sheet_data_url", lambda _: "data:image/jpeg;base64,test")
    outfit = _outfit(_query())

    class LLM:
        def parse(self, **_):
            return AestheticReviewBatch(reviews=[CandidateAestheticReview(
                candidate_id=outfit.id, style_identity_match=40,
                silhouette_proportion=85, pairing_coherence=85,
                color_material_harmony=85, constraint_compliance=85,
                style_drift_detected=False, style_drift_evidence=[],
                occasion_fit=85, color_harmony=85, silhouette_balance=85,
                material_coherence=85, overall_aesthetic=75,
                reason="百褶與合身剪裁本身不是訓練服證據。",
            )])

    intent = make_fashion_intent(activity_context=ActivityContext(
        activity_present=True, appearance_priority="high", functional_priority="low",
        requested_visual_identity="女團造型",
    ))
    result = AestheticReviewer(LLM()).review("女團舞", [outfit], fashion_intent=intent)[outfit.id]
    assert result.overall_aesthetic == 75
    assert not result.fatal_issues


@pytest.mark.parametrize("mode", [
    "appearance_led_performance", "functional_training", "mixed", "ordinary_occasion",
])
def test_activity_context_flows_through_agents_without_changing_queries(mode):
    intent = make_fashion_intent(
        activity_context=ActivityContext(
            activity="舞蹈", activity_mode=mode, primary_goal="使用者指定造型",
            minimum_functional_requirements=["基本活動"],
        ),
        forbidden_style_drift=["運動褲"],
    )
    intent = FashionIntentInterpreter(FakeIntentLLM(intent)).interpret(
        raw_user_text="棕白配色跳女團舞，不要運動褲",
        requirement_summary=RequirementSummary(), audience="women",
        hard=None, style_preferences=[],
    )
    llm = FakeLLM()
    result = QueryPlanner(llm).plan("棕白配色跳女團舞", fashion_intent=intent)
    mapping = dict(zip(
        ["appearance_led_performance", "functional_training", "mixed", "ordinary_occasion"],
        ["appearance_dominant", "function_dominant", "balanced", "not_applicable"],
    ))
    assert llm.payloads[0]["fashion_intent"]["activity_context"]["activity_mode"] == mapping[mode]
    assert llm.payloads[0]["fashion_intent"]["forbidden_style_drift"] == ["運動褲"]
    assert len(result.queries) == 12


@pytest.mark.parametrize("mode,expected_fatal", [
    ("appearance_led_performance", True), ("functional_training", False),
])
def test_practicality_cannot_rescue_failed_appearance_identity(monkeypatch, mode, expected_fatal):
    monkeypatch.setattr(module, "outfit_contact_sheet_data_url", lambda _: "data:image/jpeg;base64,test")
    outfit = _outfit(_query()).model_copy(update={"score": 0.99})
    intent = make_fashion_intent(activity_context=ActivityContext(
        activity_mode=mode, requested_visual_identity="女團造型",
    ))

    class LLM:
        def parse(self, *, content, **_):
            payload = json.loads(content[0]["text"])
            assert payload["activity_context"]["requested_visual_identity"] == "女團造型"
            return AestheticReviewBatch(reviews=[CandidateAestheticReview(
                candidate_id=outfit.id, style_identity_match=30,
                occasion_fit=100, color_harmony=100, silhouette_balance=100,
                material_coherence=100, overall_aesthetic=95,
                style_drift_detected=expected_fatal,
                style_drift_evidence=["可見專業訓練服的機能結構"] if expected_fatal else [],
                reason="服裝看似運動訓練款，未呈現所要求的舞台造型。",
            )])

    reviews = AestheticReviewer(LLM()).review("女團翻跳", [outfit], fashion_intent=intent)
    review = reviews[outfit.id]
    assert not review.fatal_issues
    result = apply_aesthetic_reviews([outfit], reviews, final_count=1, fashion_intent=intent)[0]
    if expected_fatal:
        assert review.overall_aesthetic <= 49
        assert result.score <= 0.49
    else:
        assert review.overall_aesthetic == 95


def test_missing_required_identity_score_uses_local_fallback_without_retry(monkeypatch):
    monkeypatch.setattr(module, "outfit_contact_sheet_data_url", lambda _: "data:image/jpeg;base64,test")
    outfit = _outfit(_query())
    calls = []

    class LLM:
        def parse(self, **_):
            calls.append(1)
            return AestheticReviewBatch(reviews=[CandidateAestheticReview(
                candidate_id=outfit.id, style_identity_match=None if len(calls) == 1 else 85,
                occasion_fit=80, color_harmony=80, silhouette_balance=80,
                material_coherence=80, overall_aesthetic=80, reason="舞台比例清楚。",
            )])

    reviewer = AestheticReviewer(LLM())
    result = reviewer.review("舞台表演", [outfit], fashion_intent=make_fashion_intent(
        activity_context=ActivityContext(activity_mode="appearance_led_performance"),
    ))
    assert len(calls) == 1
    assert reviewer.last_debug["attempts"][0]["local_fallbacks"][0]["candidate_id"] == outfit.id
    assert result[outfit.id].style_identity_match == 80
    assert "style_identity_match" in result[outfit.id].local_fallback_fields
