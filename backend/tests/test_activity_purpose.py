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
    assert llm.payloads[0]["fashion_intent"]["activity_context"]["activity_mode"] == mode
    assert llm.payloads[0]["fashion_intent"]["forbidden_style_drift"] == ["運動褲"]
    assert len(result.queries) == 12


@pytest.mark.parametrize("mode,expected_fatal", [
    ("appearance_led_performance", True), ("functional_training", False),
])
def test_practicality_cannot_rescue_failed_appearance_identity(monkeypatch, mode, expected_fatal):
    monkeypatch.setattr(module, "outfit_contact_sheet_data_url", lambda _: "data:image/jpeg;base64,test")
    outfit = _outfit(_query()).model_copy(update={"score": 0.99})
    intent = make_fashion_intent(activity_context=ActivityContext(activity_mode=mode))

    class LLM:
        def parse(self, *, content, **_):
            payload = json.loads(content[0]["text"])
            assert payload["activity_context"]["activity_mode"] == mode
            return AestheticReviewBatch(reviews=[CandidateAestheticReview(
                candidate_id=outfit.id, style_identity_match=30,
                occasion_fit=100, color_harmony=100, silhouette_balance=100,
                material_coherence=100, overall_aesthetic=95,
                reason="服裝看似運動訓練款，未呈現所要求的舞台造型。",
            )])

    reviews = AestheticReviewer(LLM()).review("女團翻跳", [outfit], fashion_intent=intent)
    review = reviews[outfit.id]
    assert bool(review.fatal_issues) == expected_fatal
    result = apply_aesthetic_reviews([outfit], reviews, final_count=1)[0]
    if expected_fatal:
        assert review.overall_aesthetic <= 49
        assert result.score <= 0.49
    else:
        assert review.overall_aesthetic == 95


def test_missing_required_identity_score_is_retried(monkeypatch):
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
    assert len(calls) == 2
    assert reviewer.last_debug["attempts"][0]["incomplete_review_ids"] == [outfit.id]
    assert result[outfit.id].style_identity_match == 85
