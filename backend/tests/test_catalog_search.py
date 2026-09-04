from app.models.cloth import Cloth
from app.services import catalog_search


class FakeRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return FakeRows(self.rows)


def test_free_text_catalog_search_uses_fashion_clip_and_returns_similarity(monkeypatch) -> None:
    encoded = []
    monkeypatch.setattr(
        catalog_search.fashion_clip,
        "encode_texts",
        lambda texts: encoded.append(texts) or [[0.0] * 512],
    )
    cloth = Cloth(
        id=1,
        product_display_name="White Summer Dress",
        garment_zone="one_piece",
        image_path="/data/images/1.jpg",
        image_url="/media/1.jpg",
        price=1200,
        currency="INR",
    )
    db = FakeSession([(cloth, 0.18)])

    results = catalog_search.search_catalog_items(
        db,
        "lightweight white summer dress",
        20,
        zone="one_piece",
        audience="women",
    )

    assert encoded == [["lightweight white summer dress"]]
    assert results[0].id == 1
    assert results[0].similarity == 0.82
    statement = str(db.statement)
    assert "clothes.garment_zone" in statement
    assert "clothes.gender IN" in statement
