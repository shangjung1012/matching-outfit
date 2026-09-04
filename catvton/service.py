from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
import hmac
import os
from typing import Literal, Protocol
import uuid

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel
from PIL import Image, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
RESULT_RETENTION_HOURS = 24
JobStatus = Literal["queued", "running", "succeeded", "failed"]
ClothType = Literal["upper", "lower", "overall"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobManifest(BaseModel):
    id: uuid.UUID
    status: JobStatus
    cloth_type: ClothType
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    error: str | None = None
    person_object_key: str | None = None
    cloth_object_key: str | None = None
    result_object_key: str | None = None


class JobView(BaseModel):
    id: uuid.UUID
    status: JobStatus
    cloth_type: ClothType
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    error: str | None = None
    result_url: str | None = None


class TryOnEngine(Protocol):
    device_name: str

    def run(self, person: Image.Image, cloth: Image.Image, cloth_type: str) -> bytes: ...


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
        self.bucket = os.getenv("MINIO_BUCKET", "catvton")
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
                    manifests.append(JobManifest.model_validate_json(self.get(item.object_name)))
                except (S3Error, ValueError):
                    continue
        return manifests

    def delete_job(self, job_id: uuid.UUID) -> None:
        for item in self.client.list_objects(
            self.bucket,
            prefix=f"jobs/{job_id}/",
            recursive=True,
        ):
            if item.object_name:
                self.delete(item.object_name)


class CatVTONEngine:
    def __init__(self) -> None:
        import torch
        from diffusers.image_processor import VaeImageProcessor
        from huggingface_hub import snapshot_download

        from model.cloth_masker import AutoMasker
        from model.pipeline import CatVTONPipeline
        from utils import init_weight_dtype

        if not torch.cuda.is_available():
            raise RuntimeError("CatVTON requires an NVIDIA CUDA GPU")

        repo_path = snapshot_download(
            repo_id=os.getenv("CATVTON_RESUME_PATH", "zhengchong/CatVTON")
        )
        self.torch = torch
        self.device_name = torch.cuda.get_device_name(0)
        self.pipeline = CatVTONPipeline(
            base_ckpt=os.getenv(
                "CATVTON_BASE_MODEL_PATH",
                "booksforcharlie/stable-diffusion-inpainting",
            ),
            attn_ckpt=repo_path,
            attn_ckpt_version="mix",
            weight_dtype=init_weight_dtype(os.getenv("CATVTON_MIXED_PRECISION", "bf16")),
            use_tf32=True,
            device="cuda",
            skip_safety_check=False,
        )
        self.automasker = AutoMasker(
            densepose_ckpt=os.path.join(repo_path, "DensePose"),
            schp_ckpt=os.path.join(repo_path, "SCHP"),
            device="cuda",
        )
        self.mask_processor = VaeImageProcessor(
            vae_scale_factor=8,
            do_normalize=False,
            do_binarize=True,
            do_convert_grayscale=True,
        )

    def run(self, person: Image.Image, cloth: Image.Image, cloth_type: str) -> bytes:
        from utils import resize_and_crop, resize_and_padding

        width, height = 768, 1024
        person = resize_and_crop(person.convert("RGB"), (width, height))
        cloth = resize_and_padding(cloth.convert("RGB"), (width, height))
        mask = self.mask_processor.blur(
            self.automasker(person, cloth_type)["mask"],
            blur_factor=9,
        )
        result = self.pipeline(
            image=person,
            condition_image=cloth,
            mask=mask,
            num_inference_steps=50,
            guidance_scale=2.5,
            generator=self.torch.Generator(device="cuda").manual_seed(42),
            width=width,
            height=height,
        )[0]
        output = BytesIO()
        result.save(output, format="PNG")
        return output.getvalue()


def validate_image(content: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(content))
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise HTTPException(status_code=422, detail="Only JPEG, PNG and WebP are supported")
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise HTTPException(status_code=422, detail="Image exceeds the 20MP limit")
        image.load()
        return image.convert("RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Invalid image") from error


async def read_upload(upload: UploadFile) -> bytes:
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MiB")
    validate_image(content)
    return content


def view_for(manifest: JobManifest) -> JobView:
    return JobView(
        id=manifest.id,
        status=manifest.status,
        cloth_type=manifest.cloth_type,
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
            if not manifest.person_object_key or not manifest.cloth_object_key:
                raise RuntimeError("Job input is missing")
            person_content, cloth_content = await asyncio.gather(
                asyncio.to_thread(api.state.storage.get, manifest.person_object_key),
                asyncio.to_thread(api.state.storage.get, manifest.cloth_object_key),
            )
            result = await asyncio.to_thread(
                api.state.engine.run,
                validate_image(person_content),
                validate_image(cloth_content),
                manifest.cloth_type,
            )
            validate_image(result)
            result_key = f"jobs/{manifest.id}/result.png"
            await asyncio.to_thread(api.state.storage.put, result_key, result, "image/png")
            manifest.status = "succeeded"
            manifest.result_object_key = result_key
        except Exception as error:
            manifest.status = "failed"
            manifest.error = str(error)[:2000]
        finally:
            await asyncio.gather(
                asyncio.to_thread(api.state.storage.delete, manifest.person_object_key),
                asyncio.to_thread(api.state.storage.delete, manifest.cloth_object_key),
            )
            manifest.person_object_key = None
            manifest.cloth_object_key = None
            manifest.updated_at = utcnow()
            manifest.expires_at = utcnow() + timedelta(hours=RESULT_RETENTION_HOURS)
            await save_manifest(manifest)

    async def queue_worker() -> None:
        while True:
            job_id = await api.state.queue.get()
            try:
                await process_job(job_id)
            finally:
                api.state.queue.task_done()

    async def cleanup_expired() -> None:
        manifests = await asyncio.to_thread(api.state.storage.list_manifests)
        for manifest in manifests:
            if manifest.expires_at <= utcnow():
                await asyncio.to_thread(api.state.storage.delete_job, manifest.id)

    async def cleanup_worker() -> None:
        while True:
            await asyncio.sleep(3600)
            await cleanup_expired()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage = storage or MinioJobStorage()
        await asyncio.to_thread(app.state.storage.ensure_bucket)
        app.state.engine = engine or await asyncio.to_thread(CatVTONEngine)
        app.state.queue = asyncio.Queue()
        await cleanup_expired()
        manifests = await asyncio.to_thread(app.state.storage.list_manifests)
        for manifest in manifests:
            if manifest.status in {"queued", "running"}:
                manifest.status = "queued"
                manifest.updated_at = utcnow()
                await asyncio.to_thread(app.state.storage.save_manifest, manifest)
                await app.state.queue.put(manifest.id)
        tasks = [
            asyncio.create_task(queue_worker()),
            asyncio.create_task(cleanup_worker()),
        ]
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    api = FastAPI(title="CatVTON Job API", version="1.0.0", lifespan=lifespan)

    def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
        expected = os.environ["CATVTON_API_KEY"]
        if not x_api_key or not hmac.compare_digest(x_api_key, expected):
            raise HTTPException(status_code=401, detail="Invalid API key")

    @api.get("/health")
    def health(_: None = Depends(verify_api_key)) -> dict[str, str]:
        return {"status": "ready", "device": api.state.engine.device_name}

    @api.post("/v1/jobs", response_model=JobView, status_code=202)
    async def create_job(
        person_image: UploadFile = File(...),
        cloth_image: UploadFile = File(...),
        cloth_type: ClothType = Form(...),
        _: None = Depends(verify_api_key),
    ) -> JobView:
        person_content, cloth_content = await asyncio.gather(
            read_upload(person_image),
            read_upload(cloth_image),
        )
        job_id = uuid.uuid4()
        now = utcnow()
        person_key = f"jobs/{job_id}/person"
        cloth_key = f"jobs/{job_id}/cloth"
        manifest = JobManifest(
            id=job_id,
            status="queued",
            cloth_type=cloth_type,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=RESULT_RETENTION_HOURS),
            person_object_key=person_key,
            cloth_object_key=cloth_key,
        )
        try:
            await asyncio.to_thread(
                api.state.storage.put,
                person_key,
                person_content,
                person_image.content_type or "application/octet-stream",
            )
            await asyncio.to_thread(
                api.state.storage.put,
                cloth_key,
                cloth_content,
                cloth_image.content_type or "application/octet-stream",
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
            await asyncio.to_thread(api.state.storage.delete_job, job_id)
            raise HTTPException(status_code=410, detail="Result expired")
        if manifest.status != "succeeded" or not manifest.result_object_key:
            raise HTTPException(status_code=409, detail="Result is not ready")
        content = await asyncio.to_thread(api.state.storage.get, manifest.result_object_key)
        return Response(content, media_type="image/png")

    @api.delete("/v1/jobs/{job_id}", status_code=204)
    async def delete_job(job_id: uuid.UUID, _: None = Depends(verify_api_key)) -> Response:
        await asyncio.to_thread(api.state.storage.delete_job, job_id)
        return Response(status_code=204)

    return api


app = create_app()
