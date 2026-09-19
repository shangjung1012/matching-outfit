from __future__ import annotations

import asyncio
from datetime import timedelta
import gc
from io import BytesIO
import threading
import time
import uuid

from fastapi.testclient import TestClient
from PIL import Image
import pytest

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


class CleanupFailingStorage(FakeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_list = False
        self.list_failure_raised = False

    def list_manifests(self) -> list[service.JobManifest]:
        if self.fail_next_list:
            self.fail_next_list = False
            self.list_failure_raised = True
            raise RuntimeError("injected cleanup list failure")
        return super().list_manifests()


class TerminalSaveOutageStorage(FakeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.terminal_save_failures_remaining = service.STORAGE_RETRY_ATTEMPTS
        self.terminal_save_calls = 0

    def save_manifest(self, manifest: service.JobManifest) -> None:
        if manifest.status in {"succeeded", "failed"}:
            self.terminal_save_calls += 1
            if self.terminal_save_failures_remaining:
                self.terminal_save_failures_remaining -= 1
                raise RuntimeError("injected terminal manifest outage")
        super().save_manifest(manifest)


class DeleteOutageStorage(FakeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_delete = False
        self.delete_failure_raised = threading.Event()

    def delete_job(self, job_id: uuid.UUID) -> None:
        if self.fail_next_delete:
            self.fail_next_delete = False
            self.delete_failure_raised.set()
            raise RuntimeError("injected job delete outage")
        super().delete_job(job_id)


class PausedCleanupSnapshotStorage(FakeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.pause_next_list = False
        self.snapshot_ready = threading.Event()
        self.release_snapshot = threading.Event()

    def list_manifests(self) -> list[service.JobManifest]:
        manifests = super().list_manifests()
        if self.pause_next_list:
            self.pause_next_list = False
            self.snapshot_ready.set()
            if not self.release_snapshot.wait(timeout=1):
                raise RuntimeError("test did not release cleanup snapshot")
        return manifests


class ListedObject:
    def __init__(self, object_name: str) -> None:
        self.object_name = object_name


class PartialDeleteClient:
    def __init__(self, object_names: list[str], failing_key: str) -> None:
        self.object_names = object_names
        self.failing_key = failing_key
        self.failures_remaining = service.STORAGE_RETRY_ATTEMPTS
        self.remove_calls: list[str] = []

    def list_objects(self, *_args, **_kwargs):
        return [ListedObject(name) for name in self.object_names]

    def remove_object(self, _bucket: str, object_key: str) -> None:
        self.remove_calls.append(object_key)
        if object_key == self.failing_key and self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("injected partial delete failure")
        if object_key in self.object_names:
            self.object_names.remove(object_key)


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


class SlowEngine(RecordingEngine):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()

    def run(
        self,
        person: Image.Image,
        references: dict[str, Image.Image],
    ) -> bytes:
        self.started.set()
        time.sleep(0.2)
        return super().run(person, references)


class PausingEngine(RecordingEngine):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def run(
        self,
        person: Image.Image,
        references: dict[str, Image.Image],
    ) -> bytes:
        self.started.set()
        if not self.release.wait(timeout=1):
            raise RuntimeError("test did not release inference")
        return super().run(person, references)


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


def test_validate_image_maps_decompression_bomb_to_422(monkeypatch) -> None:
    def raise_bomb(_content):
        raise Image.DecompressionBombError("too many pixels")

    monkeypatch.setattr(service.Image, "open", raise_bomb)

    with pytest.raises(service.HTTPException) as error:
        service.validate_image(png_bytes())

    assert error.value.status_code == 422
    assert error.value.detail == "Invalid image"


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
        first_completed = wait_for_status(client, first.json()["id"], "succeeded")
        completed = wait_for_status(client, second.json()["id"], "succeeded")

    assert first.status_code == 202
    assert first_completed["status"] == "succeeded"
    assert completed["status"] == "succeeded"
    assert storage.delete_failure_raised is True
    assert storage.final_save_failure_raised is True
    assert len(engine.calls) == 2
    first_manifest = storage.manifests[uuid.UUID(first.json()["id"])]
    assert first_manifest.person_object_key is None
    assert first_manifest.reference_object_keys == {}
    assert not any(
        key.startswith(f"jobs/{first.json()['id']}/") and key != first_manifest.result_object_key
        for key in storage.objects
    )
    assert "Could not delete job input" in caplog.text
    assert "Could not persist final job manifest" in caplog.text


def test_periodic_cleanup_recovers_after_transient_listing_failure(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    real_sleep = service.asyncio.sleep

    async def short_sleep(_delay: float) -> None:
        await real_sleep(0.001)

    monkeypatch.setattr(service.asyncio, "sleep", short_sleep)
    storage = CleanupFailingStorage()

    with TestClient(service.create_app(RecordingEngine(), storage)):
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
        storage.fail_next_list = True

        for _ in range(100):
            if storage.list_failure_raised and job_id not in storage.manifests:
                break
            time.sleep(0.01)

        assert storage.list_failure_raised is True
        assert job_id not in storage.manifests

    assert "Could not clean up expired jobs" in caplog.text


def test_terminal_manifest_retries_in_background_after_initial_exhaustion(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    monkeypatch.setattr(
        service,
        "FINALIZATION_RETRY_DELAY_SECONDS",
        0.001,
        raising=False,
    )
    storage = TerminalSaveOutageStorage()
    engine = RecordingEngine()

    with TestClient(service.create_app(engine, storage)) as client:
        created = post_job(
            client,
            upper_image=("upper.png", png_bytes("red"), "image/png"),
        )
        completed = wait_for_status(client, created.json()["id"], "succeeded")

    assert completed["status"] == "succeeded"
    assert storage.terminal_save_calls == service.STORAGE_RETRY_ATTEMPTS + 2
    assert len(engine.calls) == 1
    manifest = storage.manifests[uuid.UUID(created.json()["id"])]
    assert manifest.person_object_key is None
    assert manifest.reference_object_keys == {}


def test_delete_job_keeps_manifest_until_all_child_objects_are_deleted() -> None:
    job_id = uuid.uuid4()
    manifest_key = f"jobs/{job_id}/manifest.json"
    person_key = f"jobs/{job_id}/person"
    result_key = f"jobs/{job_id}/result.png"
    client = PartialDeleteClient(
        [manifest_key, person_key, result_key],
        failing_key=result_key,
    )
    storage = object.__new__(service.MinioJobStorage)
    storage.bucket = "tryon"
    storage.client = client

    with pytest.raises(RuntimeError, match="partial delete"):
        storage.delete_job(job_id)

    assert client.object_names == [manifest_key, result_key]

    storage.delete_job(job_id)

    assert client.object_names == []
    assert client.remove_calls[-1] == manifest_key


def test_shutdown_during_inference_preserves_inputs_for_startup_recovery(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()
    slow_engine = SlowEngine()

    with TestClient(service.create_app(slow_engine, storage)) as client:
        created = post_job(
            client,
            lower_image=("lower.png", png_bytes("green"), "image/png"),
        )
        job_id = uuid.UUID(created.json()["id"])
        assert slow_engine.started.wait(timeout=1)

    interrupted = storage.manifests[job_id]
    assert interrupted.status == "running"
    assert interrupted.person_object_key in storage.objects
    assert interrupted.reference_object_keys["lower"] in storage.objects

    recovery_engine = RecordingEngine()
    with TestClient(service.create_app(recovery_engine, storage)) as client:
        recovered = wait_for_status(client, str(job_id), "succeeded")

    assert recovered["status"] == "succeeded"
    assert len(recovery_engine.calls) == 1


def test_delete_cannot_be_undone_by_pending_finalization_retry(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    retry_waiting = threading.Event()
    release_retry = threading.Event()
    real_sleep = service.asyncio.sleep

    async def controlled_sleep(delay: float) -> None:
        if delay == 123:
            retry_waiting.set()
            while not release_retry.is_set():
                await real_sleep(0.001)
            return
        await real_sleep(delay)

    monkeypatch.setattr(service, "FINALIZATION_RETRY_DELAY_SECONDS", 123)
    monkeypatch.setattr(service.asyncio, "sleep", controlled_sleep)
    storage = TerminalSaveOutageStorage()
    engine = RecordingEngine()
    app = service.create_app(engine, storage)

    with TestClient(app) as client:
        created = post_job(
            client,
            upper_image=("upper.png", png_bytes("red"), "image/png"),
        )
        job_id = created.json()["id"]
        assert retry_waiting.wait(timeout=1)

        deleted = client.delete(f"/v1/jobs/{job_id}", headers=API_HEADERS)
        missing_before_retry = client.get(f"/v1/jobs/{job_id}", headers=API_HEADERS)
        release_retry.set()
        for _ in range(1000):
            if app.state.finalization_queue._unfinished_tasks == 0:
                break
            time.sleep(0.001)
        assert app.state.finalization_queue._unfinished_tasks == 0
        missing_after_retry = client.get(f"/v1/jobs/{job_id}", headers=API_HEADERS)

    assert deleted.status_code == 204
    assert missing_before_retry.status_code == 404
    assert missing_after_retry.status_code == 404
    assert storage.manifests == {}
    assert not any(key.startswith(f"jobs/{job_id}/") for key in storage.objects)
    assert len(engine.calls) == 1


def test_job_coordination_state_is_reclaimed_after_delete(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = FakeStorage()
    app = service.create_app(RecordingEngine(), storage)

    with TestClient(app) as client:
        created = post_job(
            client,
            shoe_image=("shoe.png", png_bytes("yellow"), "image/png"),
        )
        job_id = created.json()["id"]
        wait_for_status(client, job_id, "succeeded")
        deleted = client.delete(f"/v1/jobs/{job_id}", headers=API_HEADERS)
        for _ in range(1000):
            if not app.state.job_work_counts:
                break
            time.sleep(0.001)
        gc.collect()

        assert deleted.status_code == 204
        assert app.state.deleted_jobs == set()
        assert app.state.completed_deletions == set()
        assert app.state.job_work_counts == {}
        assert len(app.state.job_locks) == 0


def test_failed_delete_remains_tombstoned_until_successful_retry(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    storage = DeleteOutageStorage()
    engine = PausingEngine()
    app = service.create_app(engine, storage)

    with TestClient(app) as client:
        created = post_job(
            client,
            bag_image=("bag.png", png_bytes("blue"), "image/png"),
        )
        job_id = created.json()["id"]
        parsed_job_id = uuid.UUID(job_id)
        assert engine.started.wait(timeout=1)
        storage.fail_next_delete = True

        with pytest.raises(RuntimeError, match="job delete outage"):
            client.delete(f"/v1/jobs/{job_id}", headers=API_HEADERS)
        assert storage.delete_failure_raised.wait(timeout=1)
        engine.release.set()

        for _ in range(1000):
            if not app.state.job_work_counts:
                break
            time.sleep(0.001)
        assert app.state.job_work_counts == {}
        assert parsed_job_id in storage.manifests
        assert parsed_job_id in app.state.deleted_jobs

        retried = client.delete(f"/v1/jobs/{job_id}", headers=API_HEADERS)
        assert retried.status_code == 204
        assert parsed_job_id not in storage.manifests
        assert app.state.deleted_jobs == set()
        assert app.state.completed_deletions == set()


def test_stale_cleanup_snapshot_cannot_resurrect_deleted_job(monkeypatch) -> None:
    monkeypatch.setenv("TRYON_API_KEY", "test-key")
    cleanup_waiting = threading.Event()
    release_cleanup = threading.Event()
    cleanup_finished = threading.Event()
    cleanup_sleeps = 0
    real_sleep = service.asyncio.sleep

    async def controlled_sleep(delay: float) -> None:
        nonlocal cleanup_sleeps
        if delay == 123:
            cleanup_sleeps += 1
            if cleanup_sleeps == 1:
                cleanup_waiting.set()
                while not release_cleanup.is_set():
                    await real_sleep(0.001)
            else:
                cleanup_finished.set()
                await real_sleep(60)
            return
        await real_sleep(delay)

    monkeypatch.setattr(service, "CLEANUP_INTERVAL_SECONDS", 123)
    monkeypatch.setattr(service.asyncio, "sleep", controlled_sleep)
    storage = PausedCleanupSnapshotStorage()
    app = service.create_app(RecordingEngine(), storage)
    job_id = uuid.uuid4()
    now = service.utcnow()
    person_key = f"jobs/{job_id}/person"

    with TestClient(app) as client:
        storage.objects[person_key] = png_bytes()
        storage.save_manifest(
            service.JobManifest(
                id=job_id,
                status="failed",
                reference_types=["upper"],
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(hours=24),
                person_object_key=person_key,
            )
        )
        storage.pause_next_list = True
        assert cleanup_waiting.wait(timeout=1)
        release_cleanup.set()
        assert storage.snapshot_ready.wait(timeout=1)

        deleted = client.delete(f"/v1/jobs/{job_id}", headers=API_HEADERS)
        missing_before_cleanup = client.get(
            f"/v1/jobs/{job_id}", headers=API_HEADERS
        )
        storage.release_snapshot.set()
        assert cleanup_finished.wait(timeout=1)
        missing_after_cleanup = client.get(
            f"/v1/jobs/{job_id}", headers=API_HEADERS
        )

        assert deleted.status_code == 204
        assert missing_before_cleanup.status_code == 404
        assert missing_after_cleanup.status_code == 404
        assert job_id not in storage.manifests


def test_cancellation_safe_delete_records_success_before_propagating_cancel() -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        completed: list[bool] = []

        async def delete_operation() -> None:
            started.set()
            await release.wait()

        task = asyncio.create_task(
            service.await_cancellation_safe(
                delete_operation(),
                lambda: completed.append(True),
            )
        )
        await started.wait()
        task.cancel()
        release.set()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert completed == [True]

    asyncio.run(scenario())
