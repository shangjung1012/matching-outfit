from datetime import datetime, timedelta, timezone
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import human3d as human3d_api
from app.api import try_on as try_on_api
from app.db.session import get_db
from app.models.base import Base
from app.models.cloth import Cloth
from app.models.human3d_job import Human3DJob
from app.models.try_on_job import TryOnJob, TryOnJobReference
from app.models.user_wardrobe import UserWardrobeItem


def now() -> datetime:
    return datetime.now(timezone.utc)


class FakeTryOnClient:
    def __init__(self) -> None:
        self.remote_job_id = uuid.uuid4()
        self.status = "succeeded"
        self.result = (b"fastfit-image", "image/png")

    def get_job(self, _job_id: uuid.UUID) -> dict:
        current = now()
        return {
            "id": str(self.remote_job_id),
            "status": self.status,
            "reference_types": ["upper"],
            "created_at": current.isoformat(),
            "updated_at": current.isoformat(),
            "expires_at": (current + timedelta(hours=24)).isoformat(),
            "error": None,
            "result_url": "/v1/result" if self.status == "succeeded" else None,
        }

    def get_result(self, _job_id: uuid.UUID) -> tuple[bytes, str]:
        return self.result


class FakeHuman3DClient:
    def __init__(self) -> None:
        self.remote_job_id = uuid.uuid4()
        self.status = "queued"
        self.error: str | None = None
        self.health_result = (True, None)
        self.create_calls: list[tuple[bytes, str]] = []
        self.deleted: list[uuid.UUID] = []

    def _payload(self) -> dict:
        current = now()
        succeeded = self.status == "succeeded"
        return {
            "id": str(self.remote_job_id),
            "status": self.status,
            "created_at": current.isoformat(),
            "updated_at": current.isoformat(),
            "expires_at": (current + timedelta(hours=24)).isoformat(),
            "error": self.error,
            "artifact_type": "gaussian_splat" if succeeded else None,
            "artifact_format": "ply" if succeeded else None,
            "result_url": "/v1/result" if succeeded else None,
        }

    def health(self) -> tuple[bool, str | None]:
        return self.health_result

    def create_job(self, content: bytes, content_type: str) -> dict:
        self.create_calls.append((content, content_type))
        return self._payload()

    def get_job(self, _job_id: uuid.UUID) -> dict:
        return self._payload()

    def get_result(self, _job_id: uuid.UUID) -> tuple[bytes, str]:
        return b"ply\nformat binary_little_endian 1.0\n", "ply"

    def delete_job(self, remote_job_id: uuid.UUID) -> None:
        self.deleted.append(remote_job_id)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Cloth.__table__,
            UserWardrobeItem.__table__,
            TryOnJob.__table__,
            TryOnJobReference.__table__,
            Human3DJob.__table__,
        ],
    )
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
    fake_human3d = FakeHuman3DClient()
    monkeypatch.setattr(try_on_api, "tryon_client", fake_tryon)
    monkeypatch.setattr(human3d_api, "tryon_client", fake_tryon)
    monkeypatch.setattr(human3d_api, "human3d_client", fake_human3d)
    app = FastAPI()
    app.include_router(human3d_api.router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client, test_session, fake_tryon, fake_human3d


def add_tryon_job(
    test_session: sessionmaker[Session],
    fake_tryon: FakeTryOnClient,
    *,
    user_key: str = "demo-user",
    expires_at: datetime | None = None,
) -> uuid.UUID:
    job_id = uuid.uuid4()
    with test_session() as db:
        db.add(
            TryOnJob(
                id=job_id,
                remote_job_id=fake_tryon.remote_job_id,
                user_key=user_key,
                reference_types=["upper"],
                status="succeeded",
                expires_at=expires_at or now() + timedelta(hours=1),
            )
        )
        db.commit()
    return job_id


def test_capabilities_report_optional_service_unavailable(client) -> None:
    test_client, _, _, fake_human3d = client
    fake_human3d.health_result = (False, "LHM++ 未啟動")

    response = test_client.get("/api/human3d/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "reason": "LHM++ 未啟動",
        "artifact_formats": ["ply"],
    }


def test_create_job_forwards_completed_fastfit_result_and_persists(client) -> None:
    test_client, test_session, fake_tryon, fake_human3d = client
    tryon_job_id = add_tryon_job(test_session, fake_tryon)

    response = test_client.post(
        f"/api/try-on/jobs/{tryon_job_id}/3d",
        json={"user_key": "demo-user"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert fake_human3d.create_calls == [(b"fastfit-image", "image/png")]
    with test_session() as db:
        job = db.get(Human3DJob, uuid.UUID(response.json()["id"]))
        assert job is not None
        assert job.try_on_job_id == tryon_job_id
        assert job.remote_job_id == fake_human3d.remote_job_id


def test_create_job_rejects_missing_or_wrong_owner_fastfit_job(client) -> None:
    test_client, test_session, fake_tryon, fake_human3d = client
    tryon_job_id = add_tryon_job(test_session, fake_tryon, user_key="owner")

    missing = test_client.post(
        f"/api/try-on/jobs/{uuid.uuid4()}/3d",
        json={"user_key": "owner"},
    )
    wrong_owner = test_client.post(
        f"/api/try-on/jobs/{tryon_job_id}/3d",
        json={"user_key": "someone-else"},
    )

    assert missing.status_code == 404
    assert wrong_owner.status_code == 404
    assert fake_human3d.create_calls == []


def test_create_job_requires_completed_fastfit_result(client) -> None:
    test_client, test_session, fake_tryon, fake_human3d = client
    tryon_job_id = add_tryon_job(test_session, fake_tryon)
    fake_tryon.status = "running"

    response = test_client.post(
        f"/api/try-on/jobs/{tryon_job_id}/3d",
        json={"user_key": "demo-user"},
    )

    assert response.status_code == 409
    assert fake_human3d.create_calls == []


def test_failed_status_and_successful_result_are_proxied(client) -> None:
    test_client, test_session, fake_tryon, fake_human3d = client
    tryon_job_id = add_tryon_job(test_session, fake_tryon)
    created = test_client.post(
        f"/api/try-on/jobs/{tryon_job_id}/3d",
        json={"user_key": "demo-user"},
    ).json()
    job_id = created["id"]

    fake_human3d.status = "failed"
    fake_human3d.error = "reconstruction failed"
    failed = test_client.get(f"/api/human3d/jobs/{job_id}")
    assert failed.status_code == 200
    assert failed.json()["error"] == "reconstruction failed"

    fake_human3d.status = "succeeded"
    fake_human3d.error = None
    result = test_client.get(f"/api/human3d/jobs/{job_id}/result")
    assert result.status_code == 200
    assert result.content.startswith(b"ply\n")
    assert result.headers["x-artifact-format"] == "ply"


def test_expired_local_human3d_job_returns_gone_without_remote_call(client, monkeypatch) -> None:
    test_client, test_session, fake_tryon, fake_human3d = client
    tryon_job_id = add_tryon_job(test_session, fake_tryon)
    local_job_id = uuid.uuid4()
    with test_session() as db:
        db.add(
            Human3DJob(
                id=local_job_id,
                user_key="demo-user",
                try_on_job_id=tryon_job_id,
                remote_job_id=fake_human3d.remote_job_id,
                status="succeeded",
                artifact_format="ply",
                expires_at=now() - timedelta(seconds=1),
            )
        )
        db.commit()

    def should_not_run(_job_id):
        raise AssertionError("expired jobs must not call the remote service")

    monkeypatch.setattr(fake_human3d, "get_job", should_not_run)
    response = test_client.get(f"/api/human3d/jobs/{local_job_id}")

    assert response.status_code == 410
