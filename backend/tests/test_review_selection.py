import base64
import io

import pytest
from PIL import Image

from app.api import routes
from app.schemas import AestheticReview, SearchRequest
from app.services.aesthetic_reviewer import outfit_contact_sheet_data_url
from tests.test_recommendation_debug import _outfit, _query


@pytest.mark.parametrize("partial", [False, True])
def test_single_batch_thirty_selects_best_reviewed_ten(monkeypatch, partial):
    candidates = [
        _outfit(_query()).model_copy(update={"id": f"candidate-{index}", "score": 0.4 + index / 100})
        for index in range(30)
    ]
    calls = []

    class Reviewer:
        def __init__(self, _):
            pass

        def review(self, _request, supplied, **_):
            calls.append(len(supplied))
            return {
                candidate.id: AestheticReview(
                    occasion_fit=80, color_harmony=80, silhouette_balance=80,
                    material_coherence=80, overall_aesthetic=80, reason="配色與輪廓協調",
                )
                for candidate in (supplied[:7] if partial else supplied)
            }

    monkeypatch.setattr(routes.settings, "aesthetic_review_enabled", True)
    monkeypatch.setattr(routes.settings, "openai_api_key", "test-placeholder")
    monkeypatch.setattr(routes, "LLM", lambda: object())
    monkeypatch.setattr(routes, "AestheticReviewer", Reviewer)
    monkeypatch.setattr(routes, "hard_rules_for", lambda *_: None)
    monkeypatch.setattr(routes, "style_preferences_for", lambda *_: [])
    monkeypatch.setattr(routes, "semantic_fashion_knowledge", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(routes, "search_catalog", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(routes, "rank_outfits", lambda *_args, **_kwargs: candidates)
    monkeypatch.setattr(routes, "select_diverse", lambda pool, limit: pool[:limit])

    result = routes.recommendations(SearchRequest(queries=[_query()], include_debug=True), db=object())
    assert calls == [30]
    assert len(result.recommendations) == (7 if partial else 10)
    assert len(result.discarded_recommendations) == (23 if partial else 20)
    assert all(candidate.aesthetic_review for candidate in result.recommendations)
    assert [candidate.score for candidate in result.recommendations] == sorted(
        [candidate.score for candidate in result.recommendations], reverse=True
    )
    if not partial:
        assert result.recommendations[0].id == "candidate-29"
    else:
        assert "23 套" in result.review_note


def test_contact_sheet_keeps_full_image_and_does_not_modify_original(tmp_path):
    path = tmp_path / "original.png"
    image = Image.new("RGB", (600, 300), "red")
    image.paste("blue", (500, 0, 600, 300))
    image.save(path)
    original_bytes = path.read_bytes()
    outfit = _outfit(_query())
    outfit.items[0].image_path = str(path)
    sheet_url = outfit_contact_sheet_data_url(outfit)
    sheet = Image.open(io.BytesIO(base64.b64decode(sheet_url.split(",", 1)[1])))
    assert sheet.size == (320, 420)
    # Both ends of a wide image survive letterboxed thumbnailing.
    assert sheet.getpixel((20, 210))[0] > 200
    assert sheet.getpixel((300, 210))[2] > 200
    assert path.read_bytes() == original_bytes


def test_contact_sheet_does_not_silently_review_partial_outfit(tmp_path):
    path = tmp_path / "valid.png"
    Image.new("RGB", (100, 100)).save(path)
    outfit = _outfit(_query())
    outfit.items[0].image_path = str(path)
    outfit.items.append(outfit.items[0].model_copy(update={"id": 2, "image_path": str(tmp_path / "missing.png")}))
    assert outfit_contact_sheet_data_url(outfit) is None
