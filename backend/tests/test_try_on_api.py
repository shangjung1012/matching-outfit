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
from app.services.catvton_client import CatVTONError


def remote_payload(job_id: uuid.UUID, status: str = "queued") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": str(job_id),
        "status": status,
        "cloth_type": "upper",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "error": None,
        "result_url": f"/v1/jobs/{job_id}/result" if status == "succeeded" else None,
    }


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

    app = FastAPI()
    app.include_router(try_on_api.router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client, test_session


def png_bytes(color: str = "white") -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 48), color).save(output, format="PNG")
    return output.getvalue()


def test_capabilities_reports_unavailable(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, _ = client
    monkeypatch.setattr(
        try_on_api.catvton_client,
        "health",
        lambda: (False, "CatVTON API 尚未設定"),
    )

    response = test_client.get("/api/try-on/capabilities")

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_create_job_stores_only_remote_job_id(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, test_session = client
    remote_job_id = uuid.uuid4()
    monkeypatch.setattr(
        try_on_api.catvton_client,
        "create_job",
        lambda *_args: remote_payload(remote_job_id),
    )

    response = test_client.post(
        "/api/try-on/jobs",
        data={"cloth_type": "upper", "user_key": "demo-user"},
        files={
            "person_image": ("person.png", png_bytes(), "image/png"),
            "cloth_image": ("cloth.png", png_bytes("beige"), "image/png"),
        },
    )

    assert response.status_code == 202
    with test_session() as db:
        job = db.get(TryOnJob, uuid.UUID(response.json()["id"]))
        assert job is not None
        assert job.remote_job_id == remote_job_id


def test_create_job_rejects_invalid_image_before_remote_call(client, monkeypatch) -> None:
    test_client, _ = client
    called = False

    def create_job(*_args):
        nonlocal called
        called = True

    monkeypatch.setattr(try_on_api.catvton_client, "create_job", create_job)
    response = test_client.post(
        "/api/try-on/jobs",
        data={"cloth_type": "upper"},
        files={
            "person_image": ("person.txt", b"not-an-image", "text/plain"),
            "cloth_image": ("cloth.png", png_bytes(), "image/png"),
        },
    )

    assert response.status_code == 422
    assert called is False


def test_status_and_result_are_proxied(client, monkeypatch) -> None:
    test_client, test_session = client
    local_job_id = uuid.uuid4()
    remote_job_id = uuid.uuid4()
    with test_session() as db:
        db.add(
            TryOnJob(
                id=local_job_id,
                remote_job_id=remote_job_id,
                user_key="demo-user",
                cloth_type="upper",
                status="queued",
            )
        )
        db.commit()
    monkeypatch.setattr(
        try_on_api.catvton_client,
        "get_job",
        lambda _id: remote_payload(remote_job_id, "succeeded"),
    )
    monkeypatch.setattr(
        try_on_api.catvton_client,
        "get_result",
        lambda _id: (png_bytes("green"), "image/png"),
    )

    status = test_client.get(f"/api/try-on/jobs/{local_job_id}")
    result = test_client.get(f"/api/try-on/jobs/{local_job_id}/result")

    assert status.json()["status"] == "succeeded"
    assert status.json()["result_url"].endswith("/result")
    assert result.status_code == 200
    Image.open(BytesIO(result.content)).verify()


def test_transient_remote_failure_does_not_change_job(client, monkeypatch) -> None:
    test_client, test_session = client
    local_job_id = uuid.uuid4()
    with test_session() as db:
        db.add(
            TryOnJob(
                id=local_job_id,
                remote_job_id=uuid.uuid4(),
                user_key="demo-user",
                cloth_type="upper",
                status="running",
            )
        )
        db.commit()

    def unavailable(_job_id):
        raise CatVTONError("temporary network error")

    monkeypatch.setattr(try_on_api.catvton_client, "get_job", unavailable)
    response = test_client.get(f"/api/try-on/jobs/{local_job_id}")

    assert response.status_code == 503
    with test_session() as db:
        assert db.get(TryOnJob, local_job_id).status == "running"


def test_db_failure_deletes_remote_job(client, monkeypatch) -> None:
    test_client, _ = client
    remote_job_id = uuid.uuid4()
    deleted: list[uuid.UUID] = []
    monkeypatch.setattr(
        try_on_api.catvton_client,
        "create_job",
        lambda *_args: remote_payload(remote_job_id),
    )
    monkeypatch.setattr(
        try_on_api.catvton_client,
        "delete_job",
        lambda job_id: deleted.append(job_id),
    )

    def fail_commit(_session) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(Session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="database unavailable"):
        test_client.post(
            "/api/try-on/jobs",
            data={"cloth_type": "upper", "user_key": "demo-user"},
            files={
                "person_image": ("person.png", png_bytes(), "image/png"),
                "cloth_image": ("cloth.png", png_bytes(), "image/png"),
            },
        )

    assert deleted == [remote_job_id]
