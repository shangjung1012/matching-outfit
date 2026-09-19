from pathlib import Path

import pytest

from app.models.cloth import Cloth
from app.services import clothes_similarity


def cloth(
    item_id: int,
    *,
    garment_zone: str,
    sub_category: str | None = None,
    article_type: str | None = None,
    embedding: list[float] | None = None,
    image_path: str = "/tmp/catalog.png",
) -> Cloth:
    return Cloth(
        id=item_id,
        source_item_id=item_id,
        product_display_name=f"商品 {item_id}",
        garment_zone=garment_zone,
        sub_category=sub_category,
        article_type=article_type,
        image_path=image_path,
        image_url=f"/media/{item_id}.png",
        price=100,
        currency="TWD",
        embedding=embedding,
    )


class Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class RecordingSession:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return Result(self.rows)


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (cloth(1, garment_zone="upper_body"), "upper"),
        (cloth(2, garment_zone="lower_body"), "lower"),
        (cloth(3, garment_zone="one_piece"), "overall"),
        (cloth(4, garment_zone="accessory", sub_category="Shoes", article_type="Other Shoe"), "shoe"),
        (cloth(5, garment_zone="accessory", sub_category="Bags", article_type="Handbags"), "bag"),
        (cloth(6, garment_zone="accessory", sub_category="Accessories", article_type="Scarf"), None),
        (cloth(7, garment_zone="other", sub_category="Bags", article_type="Handbags"), None),
    ],
)
def test_reference_type_uses_exact_catalog_taxonomy(item: Cloth, expected: str | None) -> None:
    assert clothes_similarity.reference_type_for_cloth(item) == expected


def test_image_similarity_uses_exact_slot_filter_and_full_catalog_response(monkeypatch) -> None:
    candidate = cloth(
        11,
        garment_zone="accessory",
        sub_category="Shoes",
        article_type="Sneakers",
        embedding=[0.1, 0.2],
    )
    db = RecordingSession([(candidate, 0.125)])
    monkeypatch.setattr(
        clothes_similarity.fashion_clip,
        "encode_image_bytes",
        lambda _content: [0.2, 0.3],
    )

    results = clothes_similarity.find_similar_by_image(
        db,
        b"image",
        limit=12,
        garment_type="accessory",
        reference_type="shoe",
    )

    sql = str(db.statement)
    assert "clothes.garment_zone" in sql
    assert "lower(clothes.sub_category)" in sql
    assert "lower(clothes.article_type)" in sql
    assert results[0].id == 11
    assert results[0].similarity == 0.875
    assert results[0].has_embedding is True


def test_catalog_similarity_reuses_embedding_and_excludes_reference(monkeypatch) -> None:
    source = cloth(
        20,
        garment_zone="upper_body",
        embedding=[0.1, 0.2],
    )
    db = RecordingSession([])

    def unexpected_encode(_content):
        raise AssertionError("stored embedding should be reused")

    monkeypatch.setattr(
        clothes_similarity.fashion_clip,
        "encode_image_bytes",
        unexpected_encode,
    )

    assert clothes_similarity.find_similar_by_catalog_item(db, source) == []
    assert "clothes.id !=" in str(db.statement)


def test_catalog_similarity_embeds_source_image_when_embedding_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "source.png"
    image_path.write_bytes(b"catalog-image")
    source = cloth(
        30,
        garment_zone="lower_body",
        embedding=None,
        image_path=str(image_path),
    )
    db = RecordingSession([])
    received: list[bytes] = []

    def encode(content: bytes):
        received.append(content)
        return [0.4, 0.5]

    monkeypatch.setattr(clothes_similarity.fashion_clip, "encode_image_bytes", encode)

    assert clothes_similarity.find_similar_by_catalog_item(db, source) == []
    assert received == [b"catalog-image"]


def test_catalog_similarity_rejects_unsupported_or_missing_source_image(tmp_path: Path) -> None:
    unsupported = cloth(40, garment_zone="accessory", article_type="Scarf")
    missing = cloth(
        41,
        garment_zone="upper_body",
        embedding=None,
        image_path=str(tmp_path / "missing.png"),
    )

    with pytest.raises(ValueError, match="不支援"):
        clothes_similarity.find_similar_by_catalog_item(RecordingSession([]), unsupported)
    with pytest.raises(ValueError, match="無法讀取"):
        clothes_similarity.find_similar_by_catalog_item(RecordingSession([]), missing)
