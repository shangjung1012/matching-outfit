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
from app.models.user_favorite import (
    UserFavoriteItem,
    UserFavoriteOutfit,
    UserFavoriteOutfitItem,
)
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
        tables=[
            Cloth.__table__,
            UserFavoriteItem.__table__,
            UserFavoriteOutfit.__table__,
            UserFavoriteOutfitItem.__table__,
            UserStylePreference.__table__,
        ],
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
                Cloth(
                    id=3,
                    product_display_name="Blue Denim Jacket",
                    garment_zone="upper_body",
                    image_path="/data/images/3.jpg",
                    image_url="/media/3.jpg",
                    price=1800,
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
    assert empty.json() == {"user_key": "alice", "items": [], "outfits": []}

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


def test_outfit_favorites_preserve_order_and_are_set_idempotent(client) -> None:
    test_client, test_session = client

    added = test_client.put(
        "/api/favorites/alice/outfits",
        json={"item_ids": [1, 2, 2], "favorited": True},
    )
    assert added.status_code == 200
    payload = added.json()
    assert {row["item"]["id"] for row in payload["items"]} == {1, 2}
    assert len(payload["outfits"]) == 1
    assert [item["id"] for item in payload["outfits"][0]["items"]] == [1, 2]

    duplicate = test_client.put(
        "/api/favorites/alice/outfits",
        json={"item_ids": [2, 1], "favorited": True},
    )
    assert duplicate.status_code == 200
    assert len(duplicate.json()["outfits"]) == 1
    assert [item["id"] for item in duplicate.json()["outfits"][0]["items"]] == [1, 2]

    with test_session() as db:
        assert db.scalar(select(func.count()).select_from(UserFavoriteOutfit)) == 1
        favorite_rows = list(db.scalars(select(UserFavoriteItem)))
        assert all(row.is_direct is False for row in favorite_rows)

    assert test_client.get("/api/favorites/bob").json()["outfits"] == []


def test_outfit_favorites_support_multiple_bidirectional_pairings(client) -> None:
    test_client, _ = client
    for item_ids in ([1, 2], [3, 1]):
        response = test_client.put(
            "/api/favorites/alice/outfits",
            json={"item_ids": item_ids, "favorited": True},
        )
        assert response.status_code == 200

    collection = test_client.get("/api/favorites/alice").json()
    assert len(collection["outfits"]) == 2
    outfits_by_set = {
        frozenset(item["id"] for item in outfit["items"]): outfit
        for outfit in collection["outfits"]
    }
    assert set(outfits_by_set) == {frozenset({1, 2}), frozenset({1, 3})}
    assert sum(
        1 for outfit in collection["outfits"]
        if any(item["id"] == 1 for item in outfit["items"])
    ) == 2


def test_removing_outfit_only_cleans_orphaned_indirect_items(client) -> None:
    test_client, _ = client
    test_client.put(
        "/api/favorites/alice/items",
        json={"item_ids": [1], "favorited": True},
    )
    for item_ids in ([1, 2], [2, 3]):
        test_client.put(
            "/api/favorites/alice/outfits",
            json={"item_ids": item_ids, "favorited": True},
        )

    first_removed = test_client.put(
        "/api/favorites/alice/outfits",
        json={"item_ids": [2, 1], "favorited": False},
    )
    assert first_removed.status_code == 200
    assert {row["item"]["id"] for row in first_removed.json()["items"]} == {1, 2, 3}
    assert [
        {item["id"] for item in outfit["items"]}
        for outfit in first_removed.json()["outfits"]
    ] == [{2, 3}]

    second_removed = test_client.put(
        "/api/favorites/alice/outfits",
        json={"item_ids": [2, 3], "favorited": False},
    )
    assert second_removed.status_code == 200
    assert [row["item"]["id"] for row in second_removed.json()["items"]] == [1]
    assert second_removed.json()["outfits"] == []


def test_removing_single_item_dissolves_outfits_and_preserves_partners(client) -> None:
    test_client, test_session = client
    test_client.put(
        "/api/favorites/alice/outfits",
        json={"item_ids": [1, 2], "favorited": True},
    )

    removed = test_client.put(
        "/api/favorites/alice/items",
        json={"item_ids": [1], "favorited": False},
    )
    assert removed.status_code == 200
    assert removed.json()["favorite_item_ids"] == [2]
    collection = test_client.get("/api/favorites/alice").json()
    assert [row["item"]["id"] for row in collection["items"]] == [2]
    assert collection["outfits"] == []
    with test_session() as db:
        partner = db.scalar(
            select(UserFavoriteItem).where(UserFavoriteItem.cloth_id == 2)
        )
        assert partner is not None and partner.is_direct is True


def test_outfit_validation_and_missing_items_are_atomic(client) -> None:
    test_client, test_session = client
    too_small = test_client.put(
        "/api/favorites/alice/outfits",
        json={"item_ids": [1, 1], "favorited": True},
    )
    assert too_small.status_code == 422

    missing = test_client.put(
        "/api/favorites/alice/outfits",
        json={"item_ids": [1, 999], "favorited": True},
    )
    assert missing.status_code == 404
    with test_session() as db:
        assert db.scalar(select(func.count()).select_from(UserFavoriteItem)) == 0
        assert db.scalar(select(func.count()).select_from(UserFavoriteOutfit)) == 0


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


def test_outfit_reaction_is_saved_immediately_and_can_be_removed(client) -> None:
    test_client, test_session = client
    created = test_client.post(
        "/api/preferences/alice/soft/add",
        json={
            "user_key": "alice",
            "user_request": "秋天晚宴想要俐落穿搭",
            "outfit_item_ids": [2, 1],
            "preference_type": "avoid",
            "requirements": None,
        },
    )

    assert created.status_code == 201
    row = created.json()
    assert row["preference_type"] == "avoid"
    assert row["source"] == "implicit"
    assert row["origin_item_ids"] == ["2", "1"]
    assert row["confirmed_at"] is not None
    assert "White Shirt、Black Casual Trousers" in row["preference_text"]

    removed = test_client.delete(
        f"/api/preferences/alice/soft/remove/{row['id']}"
    )
    assert removed.status_code == 204
    with test_session() as db:
        assert db.get(UserStylePreference, row["id"]) is None


def test_outfit_review_summary_becomes_contextual_preference_without_product_names(client) -> None:
    test_client, _ = client
    created = test_client.post(
        "/api/preferences/alice/soft/add",
        json={
            "user_key": "alice",
            "user_request": "適合上班的簡約藍色穿搭",
            "outfit_item_ids": [2, 1],
            "preference_type": "prefer",
            "review_summary": (
                "搭配與整體：淡藍上衣和黑色寬褲形成清楚的上下對比，線條簡單且不顯厚重。"
                "唯一小缺點是上衣略偏休閒。整體乾淨、輕盈，符合上班需求。"
            ),
        },
    )

    assert created.status_code == 201
    sentence = created.json()["preference_text"]
    assert "適合上班的簡約藍色穿搭" in sentence
    assert "淡藍上衣和黑色寬褲形成清楚的上下對比" in sentence
    assert "整體乾淨、輕盈" in sentence
    assert "唯一小缺點" not in sentence
    assert "White Shirt" not in sentence
    assert "Black Casual Trousers" not in sentence


def test_avoid_outfit_review_summary_is_saved_as_contextual_preference(client) -> None:
    test_client, _ = client
    created = test_client.post(
        "/api/preferences/alice/soft/add",
        json={
            "user_key": "alice",
            "user_request": "想找適合約會的穿搭",
            "outfit_item_ids": [2, 1],
            "preference_type": "avoid",
            "review_summary": (
                "搭配與整體：上下身比例失衡，黑白對比過硬，顯得有些違和。"
                "雖然材質乾淨，但整體不適合約會時想要的柔和感。"
            ),
        },
    )

    assert created.status_code == 201
    sentence = created.json()["preference_text"]
    assert "想找適合約會的穿搭" in sentence
    assert "失衡" in sentence
    assert "違和" in sentence
    assert "不適合約會時想要的柔和感" in sentence
    assert "White Shirt" not in sentence
    assert "Black Casual Trousers" not in sentence
    assert sentence.endswith("是後續應避免的搭配方向。")


def test_single_item_reaction_has_no_context_prefix_without_user_request(client) -> None:
    test_client, _ = client
    liked = test_client.post(
        "/api/preferences/alice/soft/add",
        json={
            "user_key": "alice",
            "outfit_item_ids": [1],
            "preference_type": "prefer",
        },
    )
    assert liked.status_code == 201
    liked_row = liked.json()
    assert liked_row["preference_text"] == (
        "使用者喜歡「Black Casual Trousers」；偏好的商品特徵包含 Black、Trousers、Casual。"
    )

    disliked = test_client.post(
        "/api/preferences/alice/soft/add",
        json={
            "user_key": "alice",
            "outfit_item_ids": [2],
            "preference_type": "avoid",
        },
    )
    assert disliked.status_code == 201
    disliked_row = disliked.json()
    assert disliked_row["preference_text"] == "使用者不喜歡「White Shirt」。"
    assert disliked_row["preference_type"] == "avoid"


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
