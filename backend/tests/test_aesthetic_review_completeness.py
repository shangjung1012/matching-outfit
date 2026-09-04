import json

import pytest

from app.services import aesthetic_reviewer as module
from app.services.aesthetic_reviewer import AestheticReviewer, AestheticReviewBatch, CandidateAestheticReview
from tests.test_recommendation_debug import _outfit, _query


def review(identifier):
    return CandidateAestheticReview(
        candidate_id=identifier,
        style_identity_match=80,
        silhouette_proportion=80,
        pairing_coherence=80,
        color_material_harmony=80,
        constraint_compliance=80,
        style_drift_detected=False,
        reason="輪廓與配色協調",
    )


def candidates(count):
    return [_outfit(_query()).model_copy(update={"id": f"candidate-{index}"}) for index in range(count)]


def test_thirty_partial_response_retries_only_missing_and_recovers_all(monkeypatch):
    monkeypatch.setattr(module, "outfit_contact_sheet_data_url", lambda _: "data:image/jpeg;base64,test")
    calls = []

    class LLM:
        def parse(self, *, content, **_):
            header = json.loads(content[0]["text"])
            ids = header["required_candidate_ids"]
            calls.append(ids)
            assert [item["candidate_id"] for item in header["candidates"]] == ids
            assert len(content) == 1 + 2 * len(ids)
            if len(calls) == 1:
                return AestheticReviewBatch(reviews=[
                    *[review(identifier) for identifier in ids[:15]],
                    review(ids[0]), review("invalid-id"),
                ])
            # Small batches still omit all but the first, exercising single retries.
            return AestheticReviewBatch(reviews=[review(ids[0])])

    reviewer = AestheticReviewer(LLM())
    result = reviewer.review("夏季度假", candidates(30))
    assert len(result) == 30
    assert all(value.overall_aesthetic == 80 for value in result.values())
    assert len(calls[0]) == 30
    assert all(set(ids).isdisjoint(calls[0][:15]) for ids in calls[1:])
    assert reviewer.last_debug["attempts"][0]["duplicate_ids"] == ["candidate-0"]
    assert reviewer.last_debug["attempts"][0]["invalid_ids"] == ["invalid-id"]
    assert reviewer.last_debug["missing_ids"] == []
    assert reviewer.last_debug["reviewed_count"] == 30


def test_permanent_model_failure_has_bounded_retries_and_diagnostics(monkeypatch):
    monkeypatch.setattr(module, "outfit_contact_sheet_data_url", lambda _: "data:image/jpeg;base64,test")

    class LLM:
        def parse(self, **_):
            raise RuntimeError("provider unavailable")

    reviewer = AestheticReviewer(LLM())
    with pytest.raises(RuntimeError, match="補審"):
        reviewer.review("度假", candidates(2))
    assert len(reviewer.last_debug["attempts"]) == 4
    assert reviewer.last_debug["missing_ids"] == ["candidate-0", "candidate-1"]
    assert all(attempt["error"] for attempt in reviewer.last_debug["attempts"])


def test_unreadable_images_reported_and_never_sent():
    reviewer = AestheticReviewer(object())
    outfits = candidates(1)
    outfits[0].items[0].image_path = None
    with pytest.raises(RuntimeError, match="No readable"):
        reviewer.review("度假", outfits)
    assert reviewer.last_debug["submitted_ids"] == []
    assert reviewer.last_debug["attempts"] == []
    assert reviewer.last_debug["image_failures"][0]["candidate_id"] == "candidate-0"
    assert reviewer.last_debug["image_failures"][0]["items"][0]["reason"] == "商品沒有本機圖片路徑"
