from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.try_on import job_is_expired as try_on_job_is_expired
from app.api.try_on import synchronize_job as synchronize_try_on_job
from app.db.session import get_db
from app.models.human3d_job import Human3DJob
from app.models.try_on_job import TryOnJob
from app.schemas.human3d import (
    Human3DCapabilities,
    Human3DCreateRequest,
    Human3DJobView,
)
from app.services.human3d_client import Human3DError, human3d_client
from app.services.tryon_client import TryOnError, tryon_client


router = APIRouter(tags=["3D human reconstruction"])
JOB_STATUSES = {"queued", "running", "succeeded", "failed"}


def job_is_expired(job: Human3DJob) -> bool:
    if job.expires_at is None:
        return False
    expires_at = job.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def parse_remote_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def apply_remote_status(job: Human3DJob, payload: dict) -> None:
    status = payload.get("status")
    if status not in JOB_STATUSES:
        raise Human3DError("Human3D 工作狀態無效")
    artifact_type = payload.get("artifact_type")
    artifact_format = payload.get("artifact_format")
    if status == "succeeded" and (
        artifact_type != "gaussian_splat" or artifact_format != "ply"
    ):
        raise Human3DError("Human3D 成品格式無效")
    job.status = status
    job.error_message = (
        payload.get("error") if isinstance(payload.get("error"), str) else None
    )
    job.artifact_format = artifact_format if isinstance(artifact_format, str) else None
    job.expires_at = parse_remote_datetime(payload.get("expires_at"))


def synchronize_job(job: Human3DJob, db: Session) -> None:
    try:
        payload = human3d_client.get_job(job.remote_job_id)
    except Human3DError as error:
        if error.status_code in {404, 410}:
            job.status = "failed"
            job.error_message = "遠端 3D 工作不存在或已過期"
            db.commit()
            return
        raise HTTPException(status_code=503, detail=str(error)) from error
    apply_remote_status(job, payload)
    db.commit()
    db.refresh(job)


def job_view(job: Human3DJob) -> Human3DJobView:
    result_url = None
    if job.status == "succeeded" and not job_is_expired(job):
        result_url = f"/api/human3d/jobs/{job.id}/result"
    return Human3DJobView(
        id=job.id,
        try_on_job_id=job.try_on_job_id,
        status=job.status,
        error=job.error_message,
        artifact_type="gaussian_splat" if job.status == "succeeded" else None,
        artifact_format=job.artifact_format,
        result_url=result_url,
        created_at=job.created_at,
        updated_at=job.updated_at,
        expires_at=job.expires_at,
    )


@router.get("/human3d/capabilities", response_model=Human3DCapabilities)
def capabilities() -> Human3DCapabilities:
    available, reason = human3d_client.health()
    return Human3DCapabilities(available=available, reason=reason)


@router.post(
    "/try-on/jobs/{try_on_job_id}/3d",
    response_model=Human3DJobView,
    status_code=202,
)
async def create_job(
    try_on_job_id: uuid.UUID,
    request: Human3DCreateRequest,
    db: Session = Depends(get_db),
) -> Human3DJobView:
    try_on_job = db.get(TryOnJob, try_on_job_id)
    if try_on_job is None or try_on_job.user_key != request.user_key:
        raise HTTPException(status_code=404, detail="找不到試穿工作")
    try:
        synchronize_try_on_job(try_on_job, db)
    except TryOnError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if try_on_job_is_expired(try_on_job):
        raise HTTPException(status_code=410, detail="試穿結果已過期")
    if try_on_job.status != "succeeded" or try_on_job.remote_job_id is None:
        raise HTTPException(status_code=409, detail="試穿結果尚未完成")
    try:
        image_content, image_type = await run_in_threadpool(
            tryon_client.get_result, try_on_job.remote_job_id
        )
        payload = await run_in_threadpool(
            human3d_client.create_job, image_content, image_type
        )
        remote_job_id = uuid.UUID(str(payload["id"]))
    except (TryOnError, Human3DError, KeyError, TypeError, ValueError) as error:
        detail = str(error) if isinstance(error, (TryOnError, Human3DError)) else "3D 工作回傳無效資料"
        raise HTTPException(status_code=503, detail=detail) from error

    job = Human3DJob(
        user_key=request.user_key,
        try_on_job_id=try_on_job.id,
        remote_job_id=remote_job_id,
        status="queued",
    )
    try:
        apply_remote_status(job, payload)
        db.add(job)
        db.commit()
        db.refresh(job)
    except Exception:
        db.rollback()
        try:
            await run_in_threadpool(human3d_client.delete_job, remote_job_id)
        except Human3DError:
            pass
        raise
    return job_view(job)


@router.get("/human3d/jobs/{job_id}", response_model=Human3DJobView)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> Human3DJobView:
    job = db.get(Human3DJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到 3D 工作")
    if job_is_expired(job):
        raise HTTPException(status_code=410, detail="3D View 已過期")
    synchronize_job(job, db)
    return job_view(job)


@router.get("/human3d/jobs/{job_id}/result")
def get_result(job_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    job = db.get(Human3DJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到 3D 工作")
    if job_is_expired(job):
        raise HTTPException(status_code=410, detail="3D View 已過期")
    synchronize_job(job, db)
    if job.status != "succeeded":
        raise HTTPException(status_code=409, detail="3D View 尚未完成")
    try:
        content, artifact_format = human3d_client.get_result(job.remote_job_id)
    except Human3DError as error:
        if error.status_code == 410:
            raise HTTPException(status_code=410, detail="3D View 已過期") from error
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="human3d-{job.id}.{artifact_format}"',
            "X-Artifact-Format": artifact_format,
        },
    )
