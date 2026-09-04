from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
import hmac
import logging
import os
import time
from typing import Literal, Protocol
import uuid

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

from engine import FastFitEngine


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
RESULT_RETENTION_HOURS = 24
STORAGE_RETRY_ATTEMPTS = 3
STORAGE_RETRY_BASE_DELAY_SECONDS = 0.05
FINALIZATION_RETRY_DELAY_SECONDS = 30
CLEANUP_INTERVAL_SECONDS = 3600
REFERENCE_TYPES = ("upper", "lower", "overall", "shoe", "bag")
logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "succeeded", "failed"]
ReferenceType = Literal["upper", "lower", "overall", "shoe", "bag"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobManifest(BaseModel):
    id: uuid.UUID
    status: JobStatus
    reference_types: list[ReferenceType]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    error: str | None = None
    person_object_key: str | None = None
    reference_object_keys: dict[str, str] = Field(default_factory=dict)
    result_object_key: str | None = None


class JobView(BaseModel):
    id: uuid.UUID
    status: JobStatus
    reference_types: list[ReferenceType]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    error: str | None = None
    result_url: str | None = None


class TryOnEngine(Protocol):
    device_name: str

    def run(
        self,
        person: Image.Image,
        references: dict[str, Image.Image],
    ) -> bytes: ...


class JobStorage(Protocol):
    def ensure_bucket(self) -> None: ...
    def put(self, object_key: str, content: bytes, content_type: str) -> None: ...
    def get(self, object_key: str) -> bytes: ...
    def delete(self, object_key: str | None) -> None: ...
    def save_manifest(self, manifest: JobManifest) -> None: ...
    def get_manifest(self, job_id: uuid.UUID) -> JobManifest | None: ...
    def list_manifests(self) -> list[JobManifest]: ...
    def delete_job(self, job_id: uuid.UUID) -> None: ...


class MinioJobStorage:
    def __init__(self) -> None:
        self.bucket = os.getenv("MINIO_BUCKET", "tryon")
        self.client = Minio(
            os.getenv("MINIO_ENDPOINT", "minio:9000"),
            access_key=os.environ["MINIO_ACCESS_KEY"],
            secret_key=os.environ["MINIO_SECRET_KEY"],
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )

    @staticmethod
    def manifest_key(job_id: uuid.UUID) -> str:
        return f"jobs/{job_id}/manifest.json"

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(
            self.bucket,
            object_key,
            BytesIO(content),
            len(content),
            content_type=content_type,
        )

    def get(self, object_key: str) -> bytes:
        response = self.client.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, object_key: str | None) -> None:
        if object_key:
            self.client.remove_object(self.bucket, object_key)

    def delete_with_retry(self, object_key: str) -> None:
        for attempt in range(1, STORAGE_RETRY_ATTEMPTS + 1):
            try:
                self.delete(object_key)
                return
            except Exception:
                logger.warning(
                    "Could not delete job object %s (attempt %s/%s)",
                    object_key,
                    attempt,
                    STORAGE_RETRY_ATTEMPTS,
                    exc_info=True,
                )
                if attempt == STORAGE_RETRY_ATTEMPTS:
                    raise
                time.sleep(STORAGE_RETRY_BASE_DELAY_SECONDS * attempt)

    def save_manifest(self, manifest: JobManifest) -> None:
        self.put(
            self.manifest_key(manifest.id),
            manifest.model_dump_json().encode(),
            "application/json",
        )

    def get_manifest(self, job_id: uuid.UUID) -> JobManifest | None:
        try:
            return JobManifest.model_validate_json(self.get(self.manifest_key(job_id)))
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject"}:
                return None
            raise

    def list_manifests(self) -> list[JobManifest]:
        manifests: list[JobManifest] = []
        for item in self.client.list_objects(self.bucket, prefix="jobs/", recursive=True):
            if item.object_name and item.object_name.endswith("/manifest.json"):
                try:
                    manifests.append(
                        JobManifest.model_validate_json(self.get(item.object_name))
                    )
                except (S3Error, ValueError):
                    continue
        return manifests

    def delete_job(self, job_id: uuid.UUID) -> None:
        manifest_key = self.manifest_key(job_id)
        object_keys = [
            item.object_name
            for item in self.client.list_objects(
                self.bucket,
                prefix=f"jobs/{job_id}/",
                recursive=True,
            )
            if item.object_name
        ]
        for object_key in object_keys:
            if object_key != manifest_key:
                self.delete_with_retry(object_key)
        if manifest_key in object_keys:
            self.delete_with_retry(manifest_key)


def validate_image(content: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(content))
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise HTTPException(
                status_code=422,
                detail="Only JPEG, PNG and WebP are supported",
            )
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise HTTPException(status_code=422, detail="Image exceeds the 20MP limit")
        image.load()
        return image.convert("RGB")
    except HTTPException:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise HTTPException(status_code=422, detail="Invalid image") from error


async def read_upload(upload: UploadFile) -> bytes:
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MiB")
    validate_image(content)
    return content


def validate_reference_types(reference_types: list[str]) -> None:
    if not reference_types:
        raise HTTPException(
            status_code=422,
            detail="At least one reference image is required",
        )
    if "overall" in reference_types and (
        "upper" in reference_types or "lower" in reference_types
    ):
        raise HTTPException(
            status_code=422,
            detail="overall cannot be combined with upper or lower",
        )


def view_for(manifest: JobManifest) -> JobView:
    return JobView(
        id=manifest.id,
        status=manifest.status,
        reference_types=manifest.reference_types,
        created_at=manifest.created_at,
        updated_at=manifest.updated_at,
        expires_at=manifest.expires_at,
        error=manifest.error,
        result_url=(
            f"/v1/jobs/{manifest.id}/result"
            if manifest.status == "succeeded" and manifest.result_object_key
            else None
        ),
    )


def create_app(
    engine: TryOnEngine | None = None,
    storage: JobStorage | None = None,
) -> FastAPI:
    def job_lock(job_id: uuid.UUID) -> asyncio.Lock:
        lock = api.state.job_locks.get(job_id)
        if lock is None:
            lock = asyncio.Lock()
            api.state.job_locks[job_id] = lock
        return lock

    async def save_manifest(manifest: JobManifest) -> None:
        await asyncio.to_thread(api.state.storage.save_manifest, manifest)

    async def save_manifest_with_retry(
        manifest: JobManifest,
        description: str,
    ) -> None:
        for attempt in range(1, STORAGE_RETRY_ATTEMPTS + 1):
            try:
                await save_manifest(manifest)
                return
            except Exception:
                logger.warning(
                    "Could not persist %s for job %s (attempt %s/%s)",
                    description,
                    manifest.id,
                    attempt,
                    STORAGE_RETRY_ATTEMPTS,
                    exc_info=True,
                )
                if attempt == STORAGE_RETRY_ATTEMPTS:
                    raise
                await asyncio.sleep(STORAGE_RETRY_BASE_DELAY_SECONDS * attempt)

    async def delete_input_with_retry(
        job_id: uuid.UUID,
        object_key: str,
    ) -> bool:
        for attempt in range(1, STORAGE_RETRY_ATTEMPTS + 1):
            try:
                await asyncio.to_thread(api.state.storage.delete, object_key)
                return True
            except Exception:
                logger.warning(
                    "Could not delete job input %s for job %s (attempt %s/%s)",
                    object_key,
                    job_id,
                    attempt,
                    STORAGE_RETRY_ATTEMPTS,
                    exc_info=True,
                )
                if attempt < STORAGE_RETRY_ATTEMPTS:
                    await asyncio.sleep(STORAGE_RETRY_BASE_DELAY_SECONDS * attempt)
        return False

    async def delete_job_inputs(manifest: JobManifest) -> bool:
        targets: list[tuple[str | None, str]] = []
        if manifest.person_object_key:
            targets.append((None, manifest.person_object_key))
        targets.extend(manifest.reference_object_keys.items())
        if not targets:
            return False

        delete_results = await asyncio.gather(
            *(
                delete_input_with_retry(manifest.id, object_key)
                for _, object_key in targets
            )
        )
        changed = False
        for (reference_type, object_key), deleted in zip(targets, delete_results):
            if not deleted:
                continue
            changed = True
            if reference_type is None:
                if manifest.person_object_key == object_key:
                    manifest.person_object_key = None
            elif manifest.reference_object_keys.get(reference_type) == object_key:
                manifest.reference_object_keys.pop(reference_type)
        return changed

    async def finalize_manifest(manifest: JobManifest) -> bool:
        try:
            await save_manifest_with_retry(manifest, "final job manifest")
        except Exception:
            logger.exception(
                "Could not persist final job manifest for job %s after retries",
                manifest.id,
            )
            return False

        if await delete_job_inputs(manifest):
            manifest.updated_at = utcnow()
            try:
                await save_manifest_with_retry(
                    manifest,
                    "input cleanup manifest",
                )
            except Exception:
                logger.exception(
                    "Could not persist input cleanup manifest for job %s "
                    "after retries",
                    manifest.id,
                )
        return True

    async def process_job(job_id: uuid.UUID) -> None:
        manifest = await asyncio.to_thread(api.state.storage.get_manifest, job_id)
        if manifest is None:
            return
        try:
            async with job_lock(job_id):
                if job_id in api.state.deleted_jobs:
                    return
                manifest.status = "running"
                manifest.error = None
                manifest.updated_at = utcnow()
                await save_manifest(manifest)
            if not manifest.person_object_key or not manifest.reference_object_keys:
                raise RuntimeError("Job input is missing")
            person_content = await asyncio.to_thread(
                api.state.storage.get,
                manifest.person_object_key,
            )
            reference_contents = await asyncio.gather(
                *(
                    asyncio.to_thread(api.state.storage.get, object_key)
                    for object_key in manifest.reference_object_keys.values()
                )
            )
            references = {
                reference_type: validate_image(content)
                for reference_type, content in zip(
                    manifest.reference_object_keys,
                    reference_contents,
                )
            }
            result = await asyncio.to_thread(
                api.state.engine.run,
                validate_image(person_content),
                references,
            )
            validate_image(result)
            result_key = f"jobs/{manifest.id}/result.png"
            async with job_lock(job_id):
                if job_id in api.state.deleted_jobs:
                    return
                await asyncio.to_thread(
                    api.state.storage.put,
                    result_key,
                    result,
                    "image/png",
                )
                manifest.status = "succeeded"
                manifest.result_object_key = result_key
        except Exception as error:
            manifest.status = "failed"
            manifest.error = str(error)[:2000]
        finally:
            if manifest.status in {"succeeded", "failed"}:
                manifest.updated_at = utcnow()
                manifest.expires_at = utcnow() + timedelta(
                    hours=RESULT_RETENTION_HOURS
                )
                async with job_lock(job_id):
                    if job_id not in api.state.deleted_jobs:
                        if not await finalize_manifest(manifest):
                            await api.state.finalization_queue.put(manifest)

    async def queue_worker() -> None:
        while True:
            job_id = await api.state.queue.get()
            try:
                try:
                    await process_job(job_id)
                except Exception:
                    logger.exception("Unhandled error processing job %s", job_id)
            finally:
                api.state.queue.task_done()

    async def finalization_worker() -> None:
        while True:
            manifest = await api.state.finalization_queue.get()
            try:
                await asyncio.sleep(FINALIZATION_RETRY_DELAY_SECONDS)
                async with job_lock(manifest.id):
                    if manifest.id not in api.state.deleted_jobs:
                        if not await finalize_manifest(manifest):
                            await api.state.finalization_queue.put(manifest)
            finally:
                api.state.finalization_queue.task_done()

    async def cleanup_expired() -> None:
        manifests = await asyncio.to_thread(api.state.storage.list_manifests)
        for manifest in manifests:
            try:
                async with job_lock(manifest.id):
                    if manifest.expires_at <= utcnow():
                        api.state.deleted_jobs.add(manifest.id)
                        await asyncio.to_thread(
                            api.state.storage.delete_job,
                            manifest.id,
                        )
                    elif manifest.id in api.state.deleted_jobs:
                        continue
                    elif manifest.status in {"succeeded", "failed"} and (
                        manifest.person_object_key or manifest.reference_object_keys
                    ):
                        if await delete_job_inputs(manifest):
                            manifest.updated_at = utcnow()
                            await save_manifest_with_retry(
                                manifest,
                                "input cleanup manifest",
                            )
            except Exception:
                logger.exception("Could not clean up job %s", manifest.id)

    async def cleanup_worker() -> None:
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            try:
                await cleanup_expired()
            except Exception:
                logger.exception("Could not clean up expired jobs")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage = storage or MinioJobStorage()
        await asyncio.to_thread(app.state.storage.ensure_bucket)
        app.state.engine = engine or await asyncio.to_thread(FastFitEngine)
        app.state.queue = asyncio.Queue()
        app.state.finalization_queue = asyncio.Queue()
        app.state.job_locks = {}
        app.state.deleted_jobs = set()
        await cleanup_expired()
        manifests = await asyncio.to_thread(app.state.storage.list_manifests)
        for manifest in manifests:
            if (
                manifest.id not in app.state.deleted_jobs
                and manifest.status in {"queued", "running"}
            ):
                manifest.status = "queued"
                manifest.updated_at = utcnow()
                await asyncio.to_thread(app.state.storage.save_manifest, manifest)
                await app.state.queue.put(manifest.id)
        tasks = [
            asyncio.create_task(queue_worker()),
            asyncio.create_task(finalization_worker()),
            asyncio.create_task(cleanup_worker()),
        ]
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    api = FastAPI(title="FastFit Try-On Job API", version="1.0.0", lifespan=lifespan)

    def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
        expected = os.environ["TRYON_API_KEY"]
        if not x_api_key or not hmac.compare_digest(x_api_key, expected):
            raise HTTPException(status_code=401, detail="Invalid API key")

    @api.get("/health")
    def health(_: None = Depends(verify_api_key)) -> dict[str, str]:
        return {"status": "ready", "device": api.state.engine.device_name}

    @api.post("/v1/jobs", response_model=JobView, status_code=202)
    async def create_job(
        person_image: UploadFile = File(...),
        upper_image: UploadFile | None = File(default=None),
        lower_image: UploadFile | None = File(default=None),
        overall_image: UploadFile | None = File(default=None),
        shoe_image: UploadFile | None = File(default=None),
        bag_image: UploadFile | None = File(default=None),
        _: None = Depends(verify_api_key),
    ) -> JobView:
        uploads = {
            "upper": upper_image,
            "lower": lower_image,
            "overall": overall_image,
            "shoe": shoe_image,
            "bag": bag_image,
        }
        present_uploads = {
            reference_type: upload
            for reference_type, upload in uploads.items()
            if upload is not None
        }
        reference_types = list(present_uploads)
        validate_reference_types(reference_types)

        contents = await asyncio.gather(
            read_upload(person_image),
            *(read_upload(upload) for upload in present_uploads.values()),
        )
        person_content, *reference_contents = contents
        job_id = uuid.uuid4()
        now = utcnow()
        person_key = f"jobs/{job_id}/person"
        reference_keys = {
            reference_type: f"jobs/{job_id}/references/{reference_type}"
            for reference_type in reference_types
        }
        manifest = JobManifest(
            id=job_id,
            status="queued",
            reference_types=reference_types,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=RESULT_RETENTION_HOURS),
            person_object_key=person_key,
            reference_object_keys=reference_keys,
        )
        try:
            await asyncio.to_thread(
                api.state.storage.put,
                person_key,
                person_content,
                person_image.content_type or "application/octet-stream",
            )
            for (reference_type, upload), content in zip(
                present_uploads.items(),
                reference_contents,
            ):
                await asyncio.to_thread(
                    api.state.storage.put,
                    reference_keys[reference_type],
                    content,
                    upload.content_type or "application/octet-stream",
                )
            await save_manifest(manifest)
        except Exception:
            await asyncio.to_thread(api.state.storage.delete_job, job_id)
            raise
        await api.state.queue.put(job_id)
        return view_for(manifest)

    @api.get("/v1/jobs/{job_id}", response_model=JobView)
    async def get_job(job_id: uuid.UUID, _: None = Depends(verify_api_key)) -> JobView:
        manifest = await asyncio.to_thread(api.state.storage.get_manifest, job_id)
        if manifest is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return view_for(manifest)

    @api.get("/v1/jobs/{job_id}/result")
    async def get_result(job_id: uuid.UUID, _: None = Depends(verify_api_key)) -> Response:
        manifest = await asyncio.to_thread(api.state.storage.get_manifest, job_id)
        if manifest is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if manifest.expires_at <= utcnow():
            async with job_lock(job_id):
                api.state.deleted_jobs.add(job_id)
                await asyncio.to_thread(api.state.storage.delete_job, job_id)
            raise HTTPException(status_code=410, detail="Result expired")
        if manifest.status != "succeeded" or not manifest.result_object_key:
            raise HTTPException(status_code=409, detail="Result is not ready")
        content = await asyncio.to_thread(
            api.state.storage.get,
            manifest.result_object_key,
        )
        return Response(content, media_type="image/png")

    @api.delete("/v1/jobs/{job_id}", status_code=204)
    async def delete_job(job_id: uuid.UUID, _: None = Depends(verify_api_key)) -> Response:
        async with job_lock(job_id):
            api.state.deleted_jobs.add(job_id)
            await asyncio.to_thread(api.state.storage.delete_job, job_id)
        return Response(status_code=204)

    return api


app = create_app()
