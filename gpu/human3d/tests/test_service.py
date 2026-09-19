from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path
import threading
import time
import uuid

from fastapi.testclient import TestClient
from PIL import Image
import pytest

import service
from engine import ReconstructionResult


HEADERS = {"X-API-Key": "test-key"}


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 32), "white").save(output, format="PNG")
    return output.getvalue()


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.manifests: dict[uuid.UUID, service.JobManifest] = {}

    def ensure_bucket(self) -> None:
        pass

    def put(self, key: str, content: bytes, _content_type: str) -> None:
        self.objects[key] = content

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str | None) -> None:
        if key:
            self.objects.pop(key, None)

    def save_manifest(self, manifest: service.JobManifest) -> None:
        self.manifests[manifest.id] = service.JobManifest.model_validate(
            manifest.model_dump()
        )

    def get_manifest(self, job_id: uuid.UUID):
        manifest = self.manifests.get(job_id)
        return service.JobManifest.model_validate(manifest.model_dump()) if manifest else None

    def list_manifests(self):
        return [
            service.JobManifest.model_validate(item.model_dump())
            for item in self.manifests.values()
        ]

    def delete_job(self, job_id: uuid.UUID) -> None:
        self.manifests.pop(job_id, None)
        for key in list(self.objects):
            if key.startswith(f"jobs/{job_id}/"):
                self.objects.pop(key)


class FakeEngine:
    device_name = "Fake RTX 5080"
    cuda_capability = "12.0"
    model_name = "LHMPP-700M-PixelShuffle"
    model_loaded = True
    peak_gpu_memory_bytes = 0


class FakeController:
    effective_mode = "resident"

    def __init__(self, *, error: str | None = None, blocked: bool = False) -> None:
        self.error = error
        self.blocked = blocked
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def initialize(self) -> None:
        pass

    def health(self) -> dict[str, object]:
        return {"residency_mode": self.effective_mode}

    def run(self, images, output_dir: Path) -> ReconstructionResult:
        self.calls += 1
        self.started.set()
        if self.blocked and not self.release.wait(timeout=2):
            raise RuntimeError("test timed out")
        if self.error:
            raise RuntimeError(self.error)
        assert len(images) == 1
        artifact = output_dir / "result.ply"
        artifact.write_bytes(b"ply\nformat ascii 1.0\nend_header\n")
        return ReconstructionResult(artifact, "ply", peak_gpu_memory_bytes=1234)


def make_client(monkeypatch, controller=None, storage=None):
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = storage or FakeStorage()
    controller = controller or FakeController()
    return TestClient(service.create_app(FakeEngine(), storage, controller)), storage, controller


def wait_for_status(client: TestClient, job_id: str, status: str) -> dict:
    for _ in range(100):
        response = client.get(f"/v1/jobs/{job_id}", headers=HEADERS)
        if response.json()["status"] == status:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"job did not reach {status}")


def test_authentication_missing_and_invalid(monkeypatch) -> None:
    client, _, _ = make_client(monkeypatch)
    with client:
        assert client.get("/health").status_code == 401
        assert client.get("/health", headers={"X-API-Key": "wrong"}).status_code == 401


def test_missing_and_invalid_image(monkeypatch) -> None:
    client, _, _ = make_client(monkeypatch)
    with client:
        assert client.post("/v1/jobs", headers=HEADERS).status_code == 422
        response = client.post(
            "/v1/jobs",
            headers=HEADERS,
            files={"image": ("bad.png", b"not image", "image/png")},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "Invalid image"


def test_job_transitions_and_result_and_input_cleanup(monkeypatch) -> None:
    controller = FakeController(blocked=True)
    client, storage, _ = make_client(monkeypatch, controller)
    with client:
        created = client.post(
            "/v1/jobs",
            headers=HEADERS,
            files={"image": ("input.png", png_bytes(), "image/png")},
        )
        assert created.status_code == 202
        assert created.json()["status"] == "queued"
        assert controller.started.wait(timeout=1)
        running = client.get(f"/v1/jobs/{created.json()['id']}", headers=HEADERS)
        assert running.json()["status"] == "running"
        controller.release.set()
        completed = wait_for_status(client, created.json()["id"], "succeeded")
        result = client.get(completed["result_url"], headers=HEADERS)

    assert completed["artifact_type"] == "gaussian_splat"
    assert completed["artifact_format"] == "ply"
    assert completed["peak_gpu_memory_bytes"] == 1234
    assert result.status_code == 200
    assert result.content.startswith(b"ply\n")
    assert result.headers["x-artifact-format"] == "ply"
    manifest = next(iter(storage.manifests.values()))
    assert manifest.input_object_key is None


def test_failure_state_does_not_break_future_jobs(monkeypatch) -> None:
    controller = FakeController(error="CUDA extension failed")
    client, _, _ = make_client(monkeypatch, controller)
    with client:
        first = client.post(
            "/v1/jobs", headers=HEADERS,
            files={"image": ("input.png", png_bytes(), "image/png")},
        )
        failed = wait_for_status(client, first.json()["id"], "failed")
        assert failed["error"] == "CUDA extension failed"
        controller.error = None
        second = client.post(
            "/v1/jobs", headers=HEADERS,
            files={"image": ("input.png", png_bytes(), "image/png")},
        )
        wait_for_status(client, second.json()["id"], "succeeded")
    assert controller.calls == 2


def test_expired_result_is_deleted(monkeypatch) -> None:
    storage = FakeStorage()
    job_id = uuid.uuid4()
    key = f"jobs/{job_id}/result.ply"
    storage.objects[key] = b"ply"
    storage.manifests[job_id] = service.JobManifest(
        id=job_id,
        status="succeeded",
        created_at=service.utcnow() - timedelta(hours=2),
        updated_at=service.utcnow() - timedelta(hours=2),
        expires_at=service.utcnow() + timedelta(seconds=1),
        result_object_key=key,
        artifact_type="gaussian_splat",
        artifact_format="ply",
    )
    client, _, _ = make_client(monkeypatch, storage=storage)
    with client:
        storage.manifests[job_id].expires_at = service.utcnow() - timedelta(seconds=1)
        response = client.get(f"/v1/jobs/{job_id}/result", headers=HEADERS)
    assert response.status_code == 410
    assert job_id not in storage.manifests


def test_startup_cleanup_removes_expired_jobs(monkeypatch) -> None:
    storage = FakeStorage()
    job_id = uuid.uuid4()
    storage.manifests[job_id] = service.JobManifest(
        id=job_id,
        status="failed",
        created_at=service.utcnow() - timedelta(days=2),
        updated_at=service.utcnow() - timedelta(days=2),
        expires_at=service.utcnow() - timedelta(days=1),
    )
    client, _, _ = make_client(monkeypatch, storage=storage)
    with client:
        health = client.get("/health", headers=HEADERS)
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert storage.manifests == {}
