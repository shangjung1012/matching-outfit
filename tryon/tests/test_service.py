from __future__ import annotations

from datetime import timedelta
from io import BytesIO
import time
import uuid

from fastapi.testclient import TestClient
from PIL import Image

import service


API_HEADERS = {"X-API-Key": "test-key"}


def png_bytes(color: str = "white") -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 32), color).save(output, format="PNG")
    return output.getvalue()


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.manifests: dict[uuid.UUID, service.JobManifest] = {}
        self.put_calls: list[str] = []
        self.get_calls: list[str] = []
        self.delete_calls: list[str] = []

    def ensure_bucket(self) -> None:
        pass

    def put(self, key: str, content: bytes, _content_type: str) -> None:
        self.put_calls.append(key)
        self.objects[key] = content

    def get(self, key: str) -> bytes:
        self.get_calls.append(key)
        return self.objects[key]

    def delete(self, key: str | None) -> None:
        if key:
            self.delete_calls.append(key)
            self.objects.pop(key, None)

    def save_manifest(self, manifest: service.JobManifest) -> None:
        self.manifests[manifest.id] = service.JobManifest.model_validate(
            manifest.model_dump()
        )

    def get_manifest(self, job_id: uuid.UUID) -> service.JobManifest | None:
        manifest = self.manifests.get(job_id)
        return (
            service.JobManifest.model_validate(manifest.model_dump())
            if manifest
            else None
        )

    def list_manifests(self) -> list[service.JobManifest]:
        return [
            service.JobManifest.model_validate(item.model_dump())
            for item in self.manifests.values()
        ]

    def delete_job(self, job_id: uuid.UUID) -> None:
        self.manifests.pop(job_id, None)
        prefix = f"jobs/{job_id}/"
        for key in list(self.objects):
            if key.startswith(prefix):
                self.objects.pop(key)


class FinalizationFailingStorage(FakeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.delete_failure_raised = False
        self.final_save_failure_raised = False

    def delete(self, key: str | None) -> None:
        if key and not self.delete_failure_raised:
            self.delete_failure_raised = True
            raise RuntimeError("injected input delete failure")
        super().delete(key)

    def save_manifest(self, manifest: service.JobManifest) -> None:
        if (
            manifest.status in {"succeeded", "failed"}
            and not self.final_save_failure_raised
        ):
            self.final_save_failure_raised = True
            raise RuntimeError("injected final manifest failure")
        super().save_manifest(manifest)


class RecordingEngine:
    device_name = "Fake CUDA"

    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls: list[tuple[tuple[int, int], dict[str, tuple[int, int, int]]]] = []

    def run(
        self,
        person: Image.Image,
        references: dict[str, Image.Image],
    ) -> bytes:
        self.calls.append(
            (
                person.size,
                {name: image.getpixel((0, 0)) for name, image in references.items()},
            )
        )
        if self.error:
            raise RuntimeError(self.error)
        return png_bytes("green")


def wait_for_status(client: TestClient, job_id: str, status: str) -> dict:
    for _ in range(100):
        response = client.get(f"/v1/jobs/{job_id}", headers=API_HEADERS)
        if response.json()["status"] == status:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"Job did not reach {status}")


def post_job(client: TestClient, **references: tuple[str, bytes, str]):
    files = {"person_image": ("person.png", png_bytes(), "image/png")}
    files.update(references)
    return client.post("/v1/jobs", headers=API_HEADERS, files=files)


def test_job_lifecycle_uses_canonical_reference_order_and_delete(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()
    engine = RecordingEngine()

    with TestClient(service.create_app(engine, storage)) as client:
        unauthorized = client.get("/health")
        created = post_job(
            client,
            bag_image=("bag.png", png_bytes("blue"), "image/png"),
            upper_image=("upper.png", png_bytes("red"), "image/png"),
            shoe_image=("shoe.png", png_bytes("yellow"), "image/png"),
        )
        job_id = created.json()["id"]
        completed = wait_for_status(client, job_id, "succeeded")
        result = client.get(f"/v1/jobs/{job_id}/result", headers=API_HEADERS)
        deleted = client.delete(f"/v1/jobs/{job_id}", headers=API_HEADERS)

    assert unauthorized.status_code == 401
    assert created.status_code == 202
    assert created.json()["reference_types"] == ["upper", "shoe", "bag"]
    assert completed["reference_types"] == ["upper", "shoe", "bag"]
    assert completed["result_url"].endswith("/result")
    assert result.headers["content-type"] == "image/png"
    assert deleted.status_code == 204
    assert engine.calls == [
        (
            (24, 32),
            {"upper": (255, 0, 0), "shoe": (255, 255, 0), "bag": (0, 0, 255)},
        )
    ]
    assert storage.manifests == {}


def test_all_reference_inputs_are_stored_read_and_deleted(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()

    with TestClient(service.create_app(RecordingEngine(), storage)) as client:
        created = post_job(
            client,
            upper_image=("upper.png", png_bytes("red"), "image/png"),
            lower_image=("lower.png", png_bytes("green"), "image/png"),
            shoe_image=("shoe.png", png_bytes("blue"), "image/png"),
            bag_image=("bag.png", png_bytes("yellow"), "image/png"),
        )
        job_id = created.json()["id"]
        wait_for_status(client, job_id, "succeeded")

    input_suffixes = {
        "/person",
        "/references/upper",
        "/references/lower",
        "/references/shoe",
        "/references/bag",
    }
    assert {
        suffix
        for key in storage.put_calls
        for suffix in input_suffixes
        if key.endswith(suffix)
    } == input_suffixes
    assert {
        suffix
        for key in storage.get_calls
        for suffix in input_suffixes
        if key.endswith(suffix)
    } == input_suffixes
    assert {
        suffix
        for key in storage.delete_calls
        for suffix in input_suffixes
        if key.endswith(suffix)
    } == input_suffixes
    manifest = storage.manifests[uuid.UUID(job_id)]
    assert manifest.person_object_key is None
    assert manifest.reference_object_keys == {}
    assert manifest.result_object_key == f"jobs/{job_id}/result.png"


def test_no_reference_is_rejected_before_storage(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()
    with TestClient(service.create_app(RecordingEngine(), storage)) as client:
        response = post_job(client)

    assert response.status_code == 422
    assert storage.objects == {}
    assert storage.manifests == {}


def test_overall_conflict_is_rejected_before_storage(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()
    with TestClient(service.create_app(RecordingEngine(), storage)) as client:
        response = post_job(
            client,
            overall_image=("overall.png", png_bytes(), "image/png"),
            lower_image=("lower.png", png_bytes(), "image/png"),
        )

    assert response.status_code == 422
    assert storage.objects == {}
    assert storage.manifests == {}


def test_invalid_present_reference_is_rejected_before_storage(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()
    with TestClient(service.create_app(RecordingEngine(), storage)) as client:
        response = post_job(
            client,
            upper_image=("upper.txt", b"not an image", "text/plain"),
            bag_image=("bag.png", png_bytes(), "image/png"),
        )

    assert response.status_code == 422
    assert storage.objects == {}
    assert storage.manifests == {}


def test_failed_inference_deletes_every_input(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()
    with TestClient(
        service.create_app(RecordingEngine(error="GPU unavailable"), storage)
    ) as client:
        created = post_job(
            client,
            upper_image=("upper.png", png_bytes(), "image/png"),
            bag_image=("bag.png", png_bytes(), "image/png"),
        )
        failed = wait_for_status(client, created.json()["id"], "failed")

    assert failed["error"] == "GPU unavailable"
    assert not any(
        key.endswith(("/person", "/references/upper", "/references/bag"))
        for key in storage.objects
    )


def test_startup_recovers_running_job(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()
    job_id = uuid.uuid4()
    now = service.utcnow()
    storage.objects[f"jobs/{job_id}/person"] = png_bytes()
    storage.objects[f"jobs/{job_id}/references/lower"] = png_bytes("green")
    storage.save_manifest(
        service.JobManifest(
            id=job_id,
            status="running",
            reference_types=["lower"],
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=24),
            person_object_key=f"jobs/{job_id}/person",
            reference_object_keys={
                "lower": f"jobs/{job_id}/references/lower",
            },
        )
    )

    with TestClient(service.create_app(RecordingEngine(), storage)) as client:
        recovered = wait_for_status(client, str(job_id), "succeeded")

    assert recovered["status"] == "succeeded"
    assert recovered["reference_types"] == ["lower"]


def test_startup_removes_expired_job(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()
    job_id = uuid.uuid4()
    now = service.utcnow()
    storage.save_manifest(
        service.JobManifest(
            id=job_id,
            status="failed",
            reference_types=["shoe"],
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=2),
            expires_at=now - timedelta(hours=1),
        )
    )

    with TestClient(service.create_app(RecordingEngine(), storage)) as client:
        missing = client.get(f"/v1/jobs/{job_id}", headers=API_HEADERS)

    assert missing.status_code == 404


def test_finalization_failures_do_not_stop_queue_worker(monkeypatch, caplog) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FinalizationFailingStorage()
    engine = RecordingEngine()

    with TestClient(service.create_app(engine, storage)) as client:
        first = post_job(
            client,
            upper_image=("upper.png", png_bytes("red"), "image/png"),
            bag_image=("bag.png", png_bytes("blue"), "image/png"),
        )
        second = post_job(
            client,
            lower_image=("lower.png", png_bytes("green"), "image/png"),
        )
        completed = wait_for_status(client, second.json()["id"], "succeeded")

    assert first.status_code == 202
    assert completed["status"] == "succeeded"
    assert storage.delete_failure_raised is True
    assert storage.final_save_failure_raised is True
    assert len(engine.calls) == 2
    assert "Could not delete job input" in caplog.text
    assert "Could not persist final job manifest" in caplog.text
