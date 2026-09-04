from datetime import datetime, timezone
from io import BytesIO
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.try_on_job import TryOnJob
from app.schemas.try_on import SUPPORTED_REFERENCE_TYPES, TryOnCapabilities, TryOnJobView
from app.services.tryon_client import TryOnError, tryon_client

router = APIRouter(prefix="/try-on", tags=["virtual try-on"])

IMAGE_TYPES = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}
JOB_STATUSES = {"queued", "running", "succeeded", "failed"}


def job_is_expired(job: TryOnJob) -> bool:
    if job.expires_at is None:
        return False
    expires_at = job.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def job_view(job: TryOnJob) -> TryOnJobView:
    result_url = None
    if job.status == "succeeded" and job.remote_job_id and not job_is_expired(job):
        result_url = f"/api/try-on/jobs/{job.id}/result"
    return TryOnJobView(
        id=job.id,
        status=job.status,
        reference_types=job.reference_types,
        error=job.error_message,
        result_url=result_url,
        created_at=job.created_at,
        updated_at=job.updated_at,
        expires_at=job.expires_at,
    )


def parse_remote_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def apply_remote_status(job: TryOnJob, payload: dict) -> None:
    status = payload.get("status")
    if status not in JOB_STATUSES:
        raise TryOnError("TryOn 工作狀態無效")
    reference_types = payload.get("reference_types")
    if (
        not isinstance(reference_types, list)
        or not reference_types
        or any(reference_type not in SUPPORTED_REFERENCE_TYPES for reference_type in reference_types)
        or reference_types
        != [
            reference_type
            for reference_type in SUPPORTED_REFERENCE_TYPES
            if reference_type in reference_types
        ]
        or ("overall" in reference_types and ("upper" in reference_types or "lower" in reference_types))
    ):
        raise TryOnError("TryOn 參考圖片類型無效")
    job.status = status
    job.reference_types = reference_types
    job.error_message = payload.get("error") if isinstance(payload.get("error"), str) else None
    job.expires_at = parse_remote_datetime(payload.get("expires_at"))


def synchronize_job(job: TryOnJob, db: Session) -> None:
    if job.remote_job_id is None:
        return
    try:
        payload = tryon_client.get_job(job.remote_job_id)
    except TryOnError as error:
        if error.status_code == 404:
            job.status = "failed"
            job.error_message = "遠端 TryOn 工作不存在或已過期"
            db.commit()
            return
        raise HTTPException(status_code=503, detail=str(error)) from error
    apply_remote_status(job, payload)
    db.commit()
    db.refresh(job)


async def validated_image(upload: UploadFile) -> tuple[bytes, str]:
    content = await upload.read(settings.tryon_max_upload_bytes + 1)
    if len(content) > settings.tryon_max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"{upload.filename or '圖片'} 超過 10 MiB")
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise HTTPException(status_code=422, detail=f"{upload.filename or '檔案'} 不是有效圖片") from error
    if image_format not in IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="只支援 JPEG、PNG 或 WebP 圖片")
    if width * height > settings.tryon_max_image_pixels:
        raise HTTPException(status_code=422, detail="圖片像素超過 20MP 限制")
    return content, IMAGE_TYPES[image_format][1]


@router.get("/capabilities", response_model=TryOnCapabilities)
def capabilities() -> TryOnCapabilities:
    available, reason = tryon_client.health()
    return TryOnCapabilities(
        available=available,
        reason=reason,
        max_upload_bytes=settings.tryon_max_upload_bytes,
    )


@router.post("/jobs", response_model=TryOnJobView, status_code=202)
async def create_job(
    person_image: UploadFile = File(...),
    upper_image: UploadFile | None = File(default=None),
    lower_image: UploadFile | None = File(default=None),
    overall_image: UploadFile | None = File(default=None),
    shoe_image: UploadFile | None = File(default=None),
    bag_image: UploadFile | None = File(default=None),
    user_key: str = Form(default="demo-user", min_length=1, max_length=120),
    db: Session = Depends(get_db),
) -> TryOnJobView:
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
    if not present_uploads:
        raise HTTPException(status_code=422, detail="至少需要一張參考圖片")
    if "overall" in present_uploads and (
        "upper" in present_uploads or "lower" in present_uploads
    ):
        raise HTTPException(status_code=422, detail="overall 不可與 upper 或 lower 同時使用")

    person_content, person_content_type = await validated_image(person_image)
    references: dict[str, tuple[bytes, str]] = {}
    for reference_type, upload in present_uploads.items():
        references[reference_type] = await validated_image(upload)
    try:
        payload = await run_in_threadpool(
            tryon_client.create_job,
            person_content,
            person_content_type,
            references,
        )
        remote_job_id = uuid.UUID(str(payload["id"]))
    except (TryOnError, KeyError, TypeError, ValueError) as error:
        detail = str(error) if isinstance(error, TryOnError) else "TryOn 建立工作時回傳無效資料"
        raise HTTPException(status_code=503, detail=detail) from error

    job = TryOnJob(
        user_key=user_key,
        reference_types=list(references),
        status="queued",
        remote_job_id=remote_job_id,
    )
    try:
        apply_remote_status(job, payload)
        db.add(job)
        db.commit()
        db.refresh(job)
    except Exception:
        db.rollback()
        try:
            await run_in_threadpool(tryon_client.delete_job, remote_job_id)
        except TryOnError:
            pass
        raise
    return job_view(job)


@router.get("/jobs/{job_id}", response_model=TryOnJobView)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> TryOnJobView:
    job = db.get(TryOnJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到試穿工作")
    synchronize_job(job, db)
    return job_view(job)


@router.get("/jobs/{job_id}/result")
def get_result(job_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    job = db.get(TryOnJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到試穿工作")
    if job_is_expired(job):
        raise HTTPException(status_code=410, detail="試穿結果已過期")
    synchronize_job(job, db)
    if job.status != "succeeded" or job.remote_job_id is None:
        raise HTTPException(status_code=409, detail="試穿結果尚未完成")
    try:
        content, content_type = tryon_client.get_result(job.remote_job_id)
    except TryOnError as error:
        if error.status_code == 410:
            raise HTTPException(status_code=410, detail="試穿結果已過期") from error
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(
        content,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="try-on-{job.id}.png"'},
    )
