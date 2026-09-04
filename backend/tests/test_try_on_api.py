from datetime import datetime, timedelta, timezone
from io import BytesIO
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import try_on as try_on_api
from app.db.session import get_db
from app.models.base import Base
from app.models.try_on_job import TryOnJob
from app.services.image_inputs import validation as image_validation
from app.services.tryon_client import TryOnError


REFERENCE_TYPES = ["upper", "lower", "overall", "shoe", "bag"]


def remote_payload(
    job_id: uuid.UUID,
    status: str = "queued",
    reference_types: list[str] | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": str(job_id),
        "status": status,
        "reference_types": reference_types or ["upper"],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "error": None,
        "result_url": f"/v1/jobs/{job_id}/result" if status == "succeeded" else None,
    }


class FakeTryOnClient:
    def __init__(self) -> None:
        self.remote_job_id = uuid.uuid4()
        self.create_calls: list[tuple[bytes, str, dict[str, tuple[bytes, str]]]] = []
        self.deleted: list[uuid.UUID] = []
        self.health_result = (True, None)
        self.job_payload = remote_payload(self.remote_job_id)

    def health(self) -> tuple[bool, str | None]:
        return self.health_result

    def create_job(
        self,
        person_content: bytes,
        person_content_type: str,
        references: dict[str, tuple[bytes, str]],
    ) -> dict:
        self.create_calls.append((person_content, person_content_type, references))
        return remote_payload(self.remote_job_id, reference_types=list(references))

    def get_job(self, _remote_job_id: uuid.UUID) -> dict:
        return self.job_payload

    def get_result(self, _remote_job_id: uuid.UUID) -> tuple[bytes, str]:
        return png_bytes("green"), "image/png"

    def delete_job(self, remote_job_id: uuid.UUID) -> None:
        self.deleted.append(remote_job_id)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[TryOnJob.__table__])
    test_session: sessionmaker[Session] = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    def override_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    fake_tryon = FakeTryOnClient()
    monkeypatch.setattr(try_on_api, "tryon_client", fake_tryon, raising=False)
    app = FastAPI()
    app.include_router(try_on_api.router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client, test_session, fake_tryon


def png_bytes(color: str = "white") -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 48), color).save(output, format="PNG")
    return output.getvalue()


def test_capabilities_reports_reference_contract(client) -> None:
    test_client, _, fake_tryon = client
    fake_tryon.health_result = (False, "TryOn API 尚未設定")

    response = test_client.get("/api/try-on/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "reason": "TryOn API 尚未設定",
        "supported_reference_types": REFERENCE_TYPES,
        "max_upload_bytes": 10 * 1024 * 1024,
        "max_image_pixels": 20_000_000,
    }


def test_create_job_forwards_canonical_references_and_persists_types(client) -> None:
    test_client, test_session, fake_tryon = client

    response = test_client.post(
        "/api/try-on/jobs",
        data={"user_key": "demo-user"},
        files={
            "person_image": ("person.png", png_bytes(), "image/png"),
            "bag_image": ("bag.png", png_bytes("blue"), "image/png"),
            "upper_image": ("upper.png", png_bytes("red"), "image/png"),
            "shoe_image": ("shoe.png", png_bytes("yellow"), "image/png"),
        },
    )

    assert response.status_code == 202
    assert response.json()["reference_types"] == ["upper", "shoe", "bag"]
    _, person_type, references = fake_tryon.create_calls[0]
    assert person_type == "image/png"
    assert list(references) == ["upper", "shoe", "bag"]
    assert [content_type for _, content_type in references.values()] == [
        "image/png",
        "image/png",
        "image/png",
    ]
    with test_session() as db:
        job = db.get(TryOnJob, uuid.UUID(response.json()["id"]))
        assert job is not None
        assert job.remote_job_id == fake_tryon.remote_job_id
        assert job.reference_types == ["upper", "shoe", "bag"]


def test_create_job_requires_at_least_one_reference_before_remote_call(client) -> None:
    test_client, _, fake_tryon = client

    response = test_client.post(
        "/api/try-on/jobs",
        files={"person_image": ("person.png", png_bytes(), "image/png")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "至少需要一張參考圖片"
    assert fake_tryon.create_calls == []


@pytest.mark.parametrize("separate_type", ["upper", "lower"])
def test_create_job_rejects_overall_with_separate_clothing_before_remote_call(
    client,
    separate_type: str,
) -> None:
    test_client, _, fake_tryon = client

    response = test_client.post(
        "/api/try-on/jobs",
        files={
            "person_image": ("person.png", png_bytes(), "image/png"),
            "overall_image": ("overall.png", png_bytes("blue"), "image/png"),
            f"{separate_type}_image": (
                f"{separate_type}.png",
                png_bytes("red"),
                "image/png",
            ),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "overall 不可與 upper 或 lower 同時使用"
    assert fake_tryon.create_calls == []


@pytest.mark.parametrize("invalid_field", ["person_image", "lower_image", "bag_image"])
def test_create_job_validates_each_present_image_before_remote_call(
    client,
    invalid_field: str,
) -> None:
    test_client, _, fake_tryon = client
    files = {
        "person_image": ("person.png", png_bytes(), "image/png"),
        "lower_image": ("lower.png", png_bytes("red"), "image/png"),
        "bag_image": ("bag.png", png_bytes("blue"), "image/png"),
    }
    files[invalid_field] = ("invalid.txt", b"not-an-image", "text/plain")

    response = test_client.post("/api/try-on/jobs", files=files)

    assert response.status_code == 422
    assert "不是有效圖片" in response.json()["detail"]
    assert fake_tryon.create_calls == []


def test_create_job_maps_decompression_bomb_to_invalid_image(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, _, fake_tryon = client

    def raise_bomb(_content):
        raise Image.DecompressionBombError("too many pixels")

    monkeypatch.setattr(image_validation.Image, "open", raise_bomb)

    response = test_client.post(
        "/api/try-on/jobs",
        files={
            "person_image": ("person.png", png_bytes(), "image/png"),
            "upper_image": ("upper.png", png_bytes("red"), "image/png"),
        },
    )

    assert response.status_code == 422
    assert "不是有效圖片" in response.json()["detail"]
    assert fake_tryon.create_calls == []


def test_status_updates_reference_types_and_result_is_proxied(client) -> None:
    test_client, test_session, fake_tryon = client
    local_job_id = uuid.uuid4()
    with test_session() as db:
        db.add(
            TryOnJob(
                id=local_job_id,
                remote_job_id=fake_tryon.remote_job_id,
                user_key="demo-user",
                reference_types=["lower"],
                status="queued",
            )
        )
        db.commit()
    fake_tryon.job_payload = remote_payload(
        fake_tryon.remote_job_id,
        "succeeded",
        ["lower", "shoe"],
    )

    status = test_client.get(f"/api/try-on/jobs/{local_job_id}")
    result = test_client.get(f"/api/try-on/jobs/{local_job_id}/result")

    assert status.status_code == 200
    assert status.json()["status"] == "succeeded"
    assert status.json()["reference_types"] == ["lower", "shoe"]
    assert status.json()["result_url"].endswith("/result")
    assert result.status_code == 200
    Image.open(BytesIO(result.content)).verify()
    with test_session() as db:
        assert db.get(TryOnJob, local_job_id).reference_types == ["lower", "shoe"]


def test_transient_remote_failure_does_not_change_job(client, monkeypatch) -> None:
    test_client, test_session, fake_tryon = client
    local_job_id = uuid.uuid4()
    with test_session() as db:
        db.add(
            TryOnJob(
                id=local_job_id,
                remote_job_id=fake_tryon.remote_job_id,
                user_key="demo-user",
                reference_types=["upper", "bag"],
                status="running",
            )
        )
        db.commit()

    def unavailable(_job_id):
        raise TryOnError("temporary network error")

    monkeypatch.setattr(fake_tryon, "get_job", unavailable)
    response = test_client.get(f"/api/try-on/jobs/{local_job_id}")

    assert response.status_code == 503
    with test_session() as db:
        job = db.get(TryOnJob, local_job_id)
        assert job.status == "running"
        assert job.reference_types == ["upper", "bag"]


def test_db_failure_deletes_remote_job(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, _, fake_tryon = client

    def fail_commit(_session) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(Session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="database unavailable"):
        test_client.post(
            "/api/try-on/jobs",
            data={"user_key": "demo-user"},
            files={
                "person_image": ("person.png", png_bytes(), "image/png"),
                "upper_image": ("upper.png", png_bytes("red"), "image/png"),
            },
        )

    assert fake_tryon.deleted == [fake_tryon.remote_job_id]
