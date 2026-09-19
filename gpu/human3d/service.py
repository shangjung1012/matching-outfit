from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
import hmac
import logging
import os
from pathlib import Path
import tempfile
from typing import Protocol
import uuid
import warnings

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError

from engine import LHMEngine, ReconstructionResult
from job_models import JobManifest, JobView
from residency import ResidencyController
from storage import JobStorage, MinioJobStorage


logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "20000000"))
JOB_TTL_HOURS = int(os.getenv("JOB_TTL_HOURS", "24"))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "3600"))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReconstructionEngine(Protocol):
    device_name: str
    cuda_capability: str
    model_name: str
    model_loaded: bool
    peak_gpu_memory_bytes: int

    def load(self) -> None: ...
    def unload(self) -> None: ...
    def run(self, images: list[Image.Image], output_dir: Path) -> ReconstructionResult: ...


class ReconstructionController(Protocol):
    effective_mode: str

    def initialize(self) -> None: ...
    def run(self, images: list[Image.Image], output_dir: Path) -> ReconstructionResult: ...
    def health(self) -> dict[str, object]: ...


def validate_image(content: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
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
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise HTTPException(status_code=422, detail="Invalid image") from error


async def read_upload(upload: UploadFile) -> bytes:
    if upload.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=422, detail="Unsupported image content type")
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MiB")
    validate_image(content)
    return content


def view_for(manifest: JobManifest) -> JobView:
    return JobView(
        id=manifest.id,
        status=manifest.status,
        created_at=manifest.created_at,
        updated_at=manifest.updated_at,
        expires_at=manifest.expires_at,
        error=manifest.error,
        artifact_type=manifest.artifact_type,
        artifact_format=manifest.artifact_format,
        result_url=(
            f"/v1/jobs/{manifest.id}/result"
            if manifest.status == "succeeded" and manifest.result_object_key
            else None
        ),
        peak_gpu_memory_bytes=manifest.peak_gpu_memory_bytes,
    )


def create_app(
    engine: ReconstructionEngine | None = None,
    storage: JobStorage | None = None,
    controller: ReconstructionController | None = None,
) -> FastAPI:
    async def save_manifest(manifest: JobManifest) -> None:
        await asyncio.to_thread(api.state.storage.save_manifest, manifest)

    async def process_job(job_id: uuid.UUID) -> None:
        manifest = await asyncio.to_thread(api.state.storage.get_manifest, job_id)
        if manifest is None:
            return
        manifest.status = "running"
        manifest.error = None
        manifest.updated_at = utcnow()
        await save_manifest(manifest)
        try:
            if not manifest.input_object_key:
                raise RuntimeError("Job input is missing")
            content = await asyncio.to_thread(
                api.state.storage.get, manifest.input_object_key
            )
            image = validate_image(content)
            with tempfile.TemporaryDirectory(prefix=f"lhmpp-{job_id}-") as temp:
                result = await asyncio.to_thread(
                    api.state.controller.run,
                    [image],
                    Path(temp),
                )
                artifact = result.artifact_path.read_bytes()
            if not artifact:
                raise RuntimeError("LHM++ returned an empty artifact")
            result_key = f"jobs/{job_id}/result.{result.artifact_format}"
            await asyncio.to_thread(
                api.state.storage.put,
                result_key,
                artifact,
                "application/octet-stream",
            )
            manifest.status = "succeeded"
            manifest.result_object_key = result_key
            manifest.artifact_type = "gaussian_splat"
            manifest.artifact_format = result.artifact_format
            manifest.peak_gpu_memory_bytes = result.peak_gpu_memory_bytes
        except Exception as error:
            logger.exception("Human3D job %s failed", job_id)
            manifest.status = "failed"
            manifest.error = str(error)[:2000]
        finally:
            manifest.updated_at = utcnow()
            manifest.expires_at = utcnow() + timedelta(hours=JOB_TTL_HOURS)
            if manifest.input_object_key:
                try:
                    await asyncio.to_thread(
                        api.state.storage.delete, manifest.input_object_key
                    )
                    manifest.input_object_key = None
                except Exception:
                    logger.warning("Could not remove input for job %s", job_id, exc_info=True)
            await save_manifest(manifest)

    async def queue_worker() -> None:
        while True:
            job_id = await api.state.queue.get()
            try:
                await process_job(job_id)
            except Exception:
                logger.exception("Unhandled Human3D worker failure for %s", job_id)
            finally:
                api.state.queue.task_done()

    async def cleanup_expired() -> None:
        manifests = await asyncio.to_thread(api.state.storage.list_manifests)
        for manifest in manifests:
            try:
                if manifest.expires_at <= utcnow():
                    await asyncio.to_thread(api.state.storage.delete_job, manifest.id)
                elif (
                    manifest.status in {"succeeded", "failed"}
                    and manifest.input_object_key
                ):
                    await asyncio.to_thread(
                        api.state.storage.delete, manifest.input_object_key
                    )
                    manifest.input_object_key = None
                    manifest.updated_at = utcnow()
                    await save_manifest(manifest)
            except Exception:
                logger.exception("Could not clean Human3D job %s", manifest.id)

    async def cleanup_worker() -> None:
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            await cleanup_expired()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage = storage or MinioJobStorage()
        await asyncio.to_thread(app.state.storage.ensure_bucket)
        app.state.startup_error = None
        app.state.engine = engine
        app.state.controller = controller
        try:
            app.state.engine = app.state.engine or await asyncio.to_thread(LHMEngine)
            app.state.controller = app.state.controller or ResidencyController(
                app.state.engine
            )
            await asyncio.to_thread(app.state.controller.initialize)
        except Exception as error:
            logger.exception("Human3D runtime initialization failed")
            app.state.startup_error = str(error)
        app.state.queue = asyncio.Queue()
        await cleanup_expired()
        for manifest in await asyncio.to_thread(app.state.storage.list_manifests):
            if manifest.status in {"queued", "running"}:
                manifest.status = "queued"
                manifest.updated_at = utcnow()
                await save_manifest(manifest)
                app.state.queue.put_nowait(manifest.id)
        tasks = [
            asyncio.create_task(queue_worker()),
            asyncio.create_task(cleanup_worker()),
        ]
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    api = FastAPI(
        title="LHM++ Human3D Job API",
        version="1.0.0",
        lifespan=lifespan,
    )

    def verify_api_key(
        x_api_key: str | None = Header(default=None),
    ) -> None:
        expected = os.environ["TRYON_API_KEY"]
        if not x_api_key or not hmac.compare_digest(x_api_key, expected):
            raise HTTPException(status_code=401, detail="Invalid API key")

    def require_ready() -> None:
        if api.state.startup_error:
            raise HTTPException(status_code=503, detail=api.state.startup_error)

    @api.get("/health")
    def health(_: None = Depends(verify_api_key)) -> dict[str, object]:
        runtime = api.state.engine
        result: dict[str, object] = {
            "ok": api.state.startup_error is None,
            "model_loaded": bool(getattr(runtime, "model_loaded", False)),
            "device": getattr(runtime, "device_name", None),
            "cuda_available": runtime is not None,
            "cuda_capability": getattr(runtime, "cuda_capability", None),
            "model": getattr(runtime, "model_name", None),
            "artifact_format": "ply",
            "error": api.state.startup_error,
        }
        if api.state.controller is not None:
            result.update(api.state.controller.health())
        return result

    @api.post("/v1/jobs", response_model=JobView, status_code=202)
    async def create_job(
        image: UploadFile = File(...),
        _: None = Depends(verify_api_key),
    ) -> JobView:
        require_ready()
        content = await read_upload(image)
        job_id = uuid.uuid4()
        now = utcnow()
        input_key = f"jobs/{job_id}/input.png"
        manifest = JobManifest(
            id=job_id,
            status="queued",
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=JOB_TTL_HOURS),
            input_object_key=input_key,
        )
        try:
            await asyncio.to_thread(
                api.state.storage.put,
                input_key,
                content,
                image.content_type or "application/octet-stream",
            )
            await save_manifest(manifest)
        except Exception:
            await asyncio.to_thread(api.state.storage.delete_job, job_id)
            raise
        api.state.queue.put_nowait(job_id)
        return view_for(manifest)

    @api.get("/v1/jobs/{job_id}", response_model=JobView)
    async def get_job(
        job_id: uuid.UUID,
        _: None = Depends(verify_api_key),
    ) -> JobView:
        manifest = await asyncio.to_thread(api.state.storage.get_manifest, job_id)
        if manifest is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return view_for(manifest)

    @api.get("/v1/jobs/{job_id}/result")
    async def get_result(
        job_id: uuid.UUID,
        _: None = Depends(verify_api_key),
    ) -> Response:
        manifest = await asyncio.to_thread(api.state.storage.get_manifest, job_id)
        if manifest is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if manifest.expires_at <= utcnow():
            await asyncio.to_thread(api.state.storage.delete_job, job_id)
            raise HTTPException(status_code=410, detail="Result expired")
        if manifest.status != "succeeded" or not manifest.result_object_key:
            raise HTTPException(status_code=409, detail="Result is not ready")
        content = await asyncio.to_thread(
            api.state.storage.get, manifest.result_object_key
        )
        return Response(
            content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'inline; filename="human3d-{job_id}.ply"',
                "X-Artifact-Format": manifest.artifact_format or "ply",
            },
        )

    @api.delete("/v1/jobs/{job_id}", status_code=204)
    async def delete_job(
        job_id: uuid.UUID,
        _: None = Depends(verify_api_key),
    ) -> Response:
        await asyncio.to_thread(api.state.storage.delete_job, job_id)
        return Response(status_code=204)

    return api


app = create_app()
