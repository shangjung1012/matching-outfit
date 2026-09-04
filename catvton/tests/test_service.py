from __future__ import annotations

from datetime import timedelta
from io import BytesIO
import time
import uuid

from fastapi.testclient import TestClient
from PIL import Image

from service import CatVTONEngine, JobManifest, create_app, utcnow


def png_bytes(color: str = "white") -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 32), color).save(output, format="PNG")
    return output.getvalue()


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.manifests: dict[uuid.UUID, JobManifest] = {}

    def ensure_bucket(self) -> None:
        pass

    def put(self, key: str, content: bytes, _content_type: str) -> None:
        self.objects[key] = content

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str | None) -> None:
        if key:
            self.objects.pop(key, None)

    def save_manifest(self, manifest: JobManifest) -> None:
        self.manifests[manifest.id] = JobManifest.model_validate(manifest.model_dump())

    def get_manifest(self, job_id: uuid.UUID) -> JobManifest | None:
        manifest = self.manifests.get(job_id)
        return JobManifest.model_validate(manifest.model_dump()) if manifest else None

    def list_manifests(self) -> list[JobManifest]:
        return [JobManifest.model_validate(item.model_dump()) for item in self.manifests.values()]

    def delete_job(self, job_id: uuid.UUID) -> None:
        self.manifests.pop(job_id, None)
        prefix = f"jobs/{job_id}/"
        for key in list(self.objects):
            if key.startswith(prefix):
                self.objects.pop(key)


class FakeEngine:
    device_name = "Fake CUDA"

    def run(self, _person: Image.Image, _cloth: Image.Image, _cloth_type: str) -> bytes:
        return png_bytes("green")


class FailingEngine(FakeEngine):
    def run(self, _person: Image.Image, _cloth: Image.Image, _cloth_type: str) -> bytes:
        raise RuntimeError("GPU unavailable")


class FakeGenerator:
    def manual_seed(self, _seed: int) -> "FakeGenerator":
        return self


class FakeTorch:
    def Generator(self, device: str) -> FakeGenerator:
        assert device == "cuda"
        return FakeGenerator()


class FakeAutoMasker:
    def __call__(self, person: Image.Image, _cloth_type: str) -> dict[str, Image.Image]:
        return {"mask": Image.new("L", person.size, 255)}


class FakeMaskProcessor:
    def blur(self, mask: Image.Image, blur_factor: int) -> Image.Image:
        assert blur_factor == 9
        return mask


class RecordingPipeline:
    def __init__(self) -> None:
        self.call: dict[str, tuple[int, int]] = {}

    def __call__(
        self,
        image: Image.Image,
        condition_image: Image.Image,
        mask: Image.Image,
        **kwargs,
    ) -> list[Image.Image]:
        self.call = {
            "image": image.size,
            "condition_image": condition_image.size,
            "mask": mask.size,
            "requested": (kwargs["width"], kwargs["height"]),
        }
        return [Image.new("RGB", (768, 1024), "green")]


def wait_for_status(client: TestClient, job_id: str, status: str) -> dict:
    for _ in range(50):
        response = client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": "test-key"})
        if response.json()["status"] == status:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"Job did not reach {status}")


def test_job_lifecycle_and_delete(monkeypatch) -> None:
    monkeypatch.setenv("CATVTON_API_KEY", "test-key")
    storage = FakeStorage()
    with TestClient(create_app(FakeEngine(), storage)) as client:
        unauthorized = client.get("/health")
        created = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            data={"cloth_type": "upper"},
            files={
                "person_image": ("person.png", png_bytes(), "image/png"),
                "cloth_image": ("cloth.png", png_bytes("beige"), "image/png"),
            },
        )
        job_id = created.json()["id"]
        completed = wait_for_status(client, job_id, "succeeded")
        result = client.get(
            f"/v1/jobs/{job_id}/result",
            headers={"X-API-Key": "test-key"},
        )
        deleted = client.delete(f"/v1/jobs/{job_id}", headers={"X-API-Key": "test-key"})

    assert unauthorized.status_code == 401
    assert created.status_code == 202
    assert completed["result_url"].endswith("/result")
    assert result.headers["content-type"] == "image/png"
    assert deleted.status_code == 204
    assert storage.manifests == {}


def test_failed_inference_deletes_inputs(monkeypatch) -> None:
    monkeypatch.setenv("CATVTON_API_KEY", "test-key")
    storage = FakeStorage()
    with TestClient(create_app(FailingEngine(), storage)) as client:
        created = client.post(
            "/v1/jobs",
            headers={"X-API-Key": "test-key"},
            data={"cloth_type": "upper"},
            files={
                "person_image": ("person.png", png_bytes(), "image/png"),
                "cloth_image": ("cloth.png", png_bytes(), "image/png"),
            },
        )
        failed = wait_for_status(client, created.json()["id"], "failed")

    assert failed["error"] == "GPU unavailable"
    assert not any(key.endswith("/person") or key.endswith("/cloth") for key in storage.objects)


def test_startup_recovers_running_job(monkeypatch) -> None:
    monkeypatch.setenv("CATVTON_API_KEY", "test-key")
    storage = FakeStorage()
    job_id = uuid.uuid4()
    now = utcnow()
    storage.objects[f"jobs/{job_id}/person"] = png_bytes()
    storage.objects[f"jobs/{job_id}/cloth"] = png_bytes()
    storage.save_manifest(
        JobManifest(
            id=job_id,
            status="running",
            cloth_type="upper",
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=24),
            person_object_key=f"jobs/{job_id}/person",
            cloth_object_key=f"jobs/{job_id}/cloth",
        )
    )

    with TestClient(create_app(FakeEngine(), storage)) as client:
        recovered = wait_for_status(client, str(job_id), "succeeded")

    assert recovered["status"] == "succeeded"


def test_catvton_engine_returns_result_at_original_person_size() -> None:
    pipeline = RecordingPipeline()
    engine = object.__new__(CatVTONEngine)
    engine.pipeline = pipeline
    engine.automasker = FakeAutoMasker()
    engine.mask_processor = FakeMaskProcessor()
    engine.torch = FakeTorch()

    result_content = engine.run(
        Image.new("RGB", (640, 960), "white"),
        Image.new("RGB", (320, 480), "beige"),
        "upper",
    )

    with Image.open(BytesIO(result_content)) as result:
        assert result.size == (640, 960)
    assert pipeline.call == {
        "image": (768, 1024),
        "condition_image": (768, 1024),
        "mask": (768, 1024),
        "requested": (768, 1024),
    }


def test_startup_removes_expired_job(monkeypatch) -> None:
    monkeypatch.setenv("CATVTON_API_KEY", "test-key")
    storage = FakeStorage()
    job_id = uuid.uuid4()
    now = utcnow()
    storage.save_manifest(
        JobManifest(
            id=job_id,
            status="failed",
            cloth_type="upper",
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=2),
            expires_at=now - timedelta(hours=1),
        )
    )

    with TestClient(create_app(FakeEngine(), storage)) as client:
        missing = client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": "test-key"})

    assert missing.status_code == 404
