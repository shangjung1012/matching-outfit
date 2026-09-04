from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.knowledge.snapshot import (
    build_snapshot,
    content_digest,
    decode_embedding,
    encode_embedding,
    load_snapshot,
    validate_snapshot,
    write_snapshot,
)


NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeSession:
    def __init__(self, articles):
        self.articles = articles

    def scalars(self, _statement):
        return FakeScalarResult(self.articles)


def observation(identifier: str, embedding: list[float] | None):
    return SimpleNamespace(
        observation_id=identifier,
        summary="短版外套搭配高腰長褲可拉高腰線。",
        evidence="圖片呈現短版上衣與高腰下身的比例關係。",
        audiences=["women"],
        occasions=["outing"],
        climates=[],
        seasons=["autumn"],
        times_of_day=[],
        formalities=["casual"],
        activities=["walking"],
        styles=["minimal"],
        garments=["cropped jacket", "high-rise trousers"],
        colors=[],
        materials=[],
        silhouettes=["cropped", "straight"],
        styling_actions=["balance proportions"],
        avoid_when=[],
        signal_type="timeless",
        confidence=0.9,
        embedding=embedding,
        embedding_model="test-embedding",
        is_active=True,
        reviewed_at=None,
    )


def article():
    return SimpleNamespace(
        source_url="https://example.com/article",
        source_name="example.com",
        title="Example",
        author="Editor",
        published_at=NOW,
        collected_at=NOW,
        language="zh-TW",
        article_summary="比例搭配示例。",
        extraction_notes=[],
        extraction_model="test-model",
        extracted_at=NOW,
        observations=[observation("obs_1", [0.25, -0.5])],
    )


def test_embedding_round_trip_uses_compact_base64() -> None:
    encoded = encode_embedding([0.25, -0.5])

    assert encoded is not None
    assert decode_embedding(encoded, 2) == [0.25, -0.5]


def test_snapshot_write_is_stable_when_content_did_not_change(tmp_path) -> None:
    snapshot = build_snapshot(FakeSession([article()]), 2)
    path = tmp_path / "fashion_knowledge.snapshot.json"

    assert write_snapshot(path, snapshot) is True
    first_content = path.read_text(encoding="utf-8")
    assert write_snapshot(path, build_snapshot(FakeSession([article()]), 2)) is False
    assert path.read_text(encoding="utf-8") == first_content
    assert load_snapshot(path).content_digest == snapshot.content_digest


def test_snapshot_checksum_detects_modified_content() -> None:
    snapshot = build_snapshot(FakeSession([article()]), 2)
    snapshot.articles[0].article_summary = "內容遭到修改。"

    with pytest.raises(ValueError, match="checksum"):
        validate_snapshot(snapshot)


def test_digest_is_independent_of_generation_time() -> None:
    first = build_snapshot(FakeSession([article()]), 2)
    second = build_snapshot(FakeSession([article()]), 2)

    assert first.content_digest == second.content_digest
    assert first.content_digest == content_digest(first.articles, 2)
