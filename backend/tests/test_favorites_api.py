from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import router
from app.db.session import get_db
from app.models.base import Base
from app.models.cloth import Cloth
from app.models.user_favorite import UserFavoriteItem
from app.models.user_preference import UserStylePreference


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[Cloth.__table__, UserFavoriteItem.__table__, UserStylePreference.__table__],
    )
    test_session: sessionmaker[Session] = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    with test_session() as db:
        db.add_all(
            [
                Cloth(
                    id=1,
                    product_display_name="Black Casual Trousers",
                    garment_zone="lower_body",
                    image_path="/data/images/1.jpg",
                    image_url="/media/1.jpg",
                    price=1200,
                    currency="INR",
                    base_colour="Black",
                    article_type="Trousers",
                    usage="Casual",
                ),
                Cloth(
                    id=2,
                    product_display_name="White Shirt",
                    garment_zone="upper_body",
                    image_path="/data/images/2.jpg",
                    image_url="/media/2.jpg",
                    price=900,
                    currency="INR",
                ),
            ]
        )
        db.commit()

    def override_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client, test_session


def test_favorites_are_idempotent_ordered_and_isolated_by_user(client) -> None:
    test_client, _ = client

    empty = test_client.get("/api/favorites/alice")
    assert empty.status_code == 200
    assert empty.json() == {"user_key": "alice", "items": []}

    added = test_client.put(
        "/api/favorites/alice/items",
        json={"item_ids": [1, 2, 2], "favorited": True},
    )
    assert added.status_code == 200
    assert added.json() == {
        "user_key": "alice",
        "added": 2,
        "removed": 0,
        "favorite_item_ids": [1, 2],
    }

    duplicate = test_client.put(
        "/api/favorites/alice/items",
        json={"item_ids": [1, 2], "favorited": True},
    )
    assert duplicate.json()["added"] == 0

    favorites = test_client.get("/api/favorites/alice").json()["items"]
    assert [row["item"]["id"] for row in favorites] == [2, 1]
    assert all(row["favorited_at"] for row in favorites)
    assert test_client.get("/api/favorites/bob").json()["items"] == []


def test_batch_remove_and_missing_item_are_atomic(client) -> None:
    test_client, test_session = client
    missing = test_client.put(
        "/api/favorites/alice/items",
        json={"item_ids": [1, 999], "favorited": True},
    )
    assert missing.status_code == 404
    with test_session() as db:
        assert db.scalar(select(func.count()).select_from(UserFavoriteItem)) == 0

    test_client.put(
        "/api/favorites/alice/items",
        json={"item_ids": [1, 2], "favorited": True},
    )
    removed = test_client.put(
        "/api/favorites/alice/items",
        json={"item_ids": [1, 2], "favorited": False},
    )
    assert removed.json() == {
        "user_key": "alice",
        "added": 0,
        "removed": 2,
        "favorite_item_ids": [],
    }


def test_single_item_preference_is_proposed_before_it_is_persisted(client) -> None:
    test_client, test_session = client
    response = test_client.post(
        "/api/preferences/alice/soft/from-item", json={"item_id": 1}
    )

    assert response.status_code == 200
    proposal = response.json()["proposals"][0]
    assert proposal["source"] == "implicit"
    assert proposal["origin_item_ids"] == ["1"]
    assert "Black Casual Trousers" in proposal["preference_text"]
    assert "Black、Trousers、Casual" in proposal["preference_text"]
    with test_session() as db:
        assert db.scalar(select(func.count()).select_from(UserStylePreference)) == 0

    confirmed = test_client.post(
        "/api/preferences/alice/soft/confirm",
        json={"user_key": "alice", "rows": [proposal]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["created"] == 1

    with test_session() as db:
        preference_id = db.scalar(
            select(UserStylePreference.id).where(
                UserStylePreference.user_key == "alice"
            )
        )
    assert preference_id is not None
    disabled = test_client.patch(
        f"/api/preferences/alice/soft/{preference_id}",
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False


def test_identical_item_descriptions_keep_distinct_preference_origins(client) -> None:
    test_client, test_session = client
    with test_session() as db:
        second = db.get(Cloth, 2)
        assert second is not None
        second.product_display_name = "Black Casual Trousers"
        second.base_colour = "Black"
        second.article_type = "Trousers"
        second.usage = "Casual"
        db.commit()

    proposals = [
        test_client.post(
            "/api/preferences/alice/soft/from-item", json={"item_id": item_id}
        ).json()["proposals"][0]
        for item_id in (1, 2)
    ]
    assert proposals[0]["preference_text"] == proposals[1]["preference_text"]

    for proposal in proposals:
        response = test_client.post(
            "/api/preferences/alice/soft/confirm",
            json={"user_key": "alice", "rows": [proposal]},
        )
        assert response.status_code == 200
        assert response.json()["created"] == 1

    with test_session() as db:
        origins = db.scalars(
            select(UserStylePreference.origin_item_ids).where(
                UserStylePreference.user_key == "alice"
            )
        ).all()
    assert origins == [["1"], ["2"]]
