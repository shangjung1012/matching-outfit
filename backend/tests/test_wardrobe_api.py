from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.wardrobe import router
from app.core.config import settings
from app.db.session import get_db
from app.models.base import Base
from app.models.user_wardrobe import UserWardrobeItem


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 24), "blue").save(output, format="PNG")
    return output.getvalue()


def test_wardrobe_upload_uses_filename_and_keeps_favorites_private(tmp_path, monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[UserWardrobeItem.__table__])
    test_session: sessionmaker[Session] = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, "wardrobe_dir", str(tmp_path))

    def override_db():
        with test_session() as db:
            yield db

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        uploaded = client.post(
            "/api/wardrobe/alice",
            data={"category": "upper_body"},
            files={"image": ("藍色襯衫.png", png_bytes(), "image/png")},
        )
        assert uploaded.status_code == 201
        item = uploaded.json()
        assert item["name"] == "藍色襯衫"
        assert item["category"] == "upper_body"
        assert item["is_favorite"] is False
        assert len(list(tmp_path.iterdir())) == 1

        favorited = client.patch(
            f"/api/wardrobe/alice/{item['id']}/favorite",
            json={"is_favorite": True},
        )
        assert favorited.status_code == 200
        assert favorited.json()["is_favorite"] is True
        assert len(client.get("/api/wardrobe/alice?favorites_only=true").json()) == 1
        assert client.get("/api/wardrobe/bob").json() == []

        removed = client.delete(f"/api/wardrobe/alice/{item['id']}")
        assert removed.status_code == 204
        assert client.get("/api/wardrobe/alice").json() == []
        assert list(tmp_path.iterdir()) == []

