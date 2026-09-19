from datetime import datetime, timezone
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.cloth import Cloth
from app.models.human3d_job import Human3DJob
from app.models.try_on_job import TryOnJob, TryOnJobReference
from app.models.user_wardrobe import UserWardrobeItem
from app.schemas.human3d import Human3DJobView
from app.schemas.try_on import (
    SUPPORTED_REFERENCE_TYPES,
    TryOnCapabilities,
    TryOnHistoryView,
    TryOnJobReferenceView,
    TryOnJobView,
)
from app.schemas.workflow import CatalogItem
from app.schemas.wardrobe import WardrobeItemView
from app.services.clothes_similarity import reference_type_for_cloth
from app.services.tryon_client import TryOnError, tryon_client
from app.services.image_inputs.validation import validate_image, validate_image_bytes

router = APIRouter(prefix="/try-on", tags=["virtual try-on"])

JOB_STATUSES = {"queued", "running", "succeeded", "failed"}
REFERENCE_LABELS = {
    "upper": "上身",
    "lower": "下身",
    "overall": "洋裝／連身",
    "shoe": "鞋子",
    "bag": "包包",
}
WARDROBE_REFERENCE_TYPES = {
    "upper_body": "upper",
    "lower_body": "lower",
    "one_piece": "overall",
    "shoes": "shoe",
    "bags": "bag",
}


def job_is_expired(job: TryOnJob) -> bool:
    if job.expires_at is None:
        return False
    expires_at = job.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def catalog_item_view(cloth: Cloth) -> CatalogItem:
    return CatalogItem(
        id=cloth.id,
        source_item_id=cloth.source_item_id,
        product_display_name=cloth.product_display_name,
        garment_zone=cloth.garment_zone,
        image_url=cloth.image_url,
        price=cloth.price,
        original_price=cloth.original_price,
        discounted_price=cloth.discounted_price,
        currency=cloth.currency,
        brand_name=cloth.brand_name,
        age_group=cloth.age_group,
        gender=cloth.gender,
        master_category=cloth.master_category,
        sub_category=cloth.sub_category,
        article_type=cloth.article_type,
        base_colour=cloth.base_colour,
        season=cloth.season,
        year=cloth.year,
        usage=cloth.usage,
        has_embedding=cloth.embedding is not None,
    )


def wardrobe_item_view(item: UserWardrobeItem) -> WardrobeItemView:
    return WardrobeItemView(
        id=item.id,
        name=item.name,
        category=item.category,
        image_url=f"/wardrobe-media/{item.stored_filename}",
        original_filename=item.original_filename,
        is_favorite=item.is_favorite,
        created_at=item.created_at,
    )


def job_view(job: TryOnJob) -> TryOnJobView:
    result_url = None
    if job.status == "succeeded" and job.remote_job_id and not job_is_expired(job):
        result_url = f"/api/try-on/jobs/{job.id}/result"
    return TryOnJobView(
        id=job.id,
        status=job.status,
        reference_types=job.reference_types,
        references=[
            TryOnJobReferenceView(
                reference_type=reference.reference_type,
                source=reference.source,
                display_name=reference.display_name,
                image_url=reference.image_url,
                catalog_item=(
                    catalog_item_view(reference.cloth) if reference.cloth is not None else None
                ),
                wardrobe_item=(
                    wardrobe_item_view(reference.wardrobe_item)
                    if reference.wardrobe_item is not None
                    else None
                ),
            )
            for reference in job.references
        ],
        error=job.error_message,
        result_url=result_url,
        created_at=job.created_at,
        updated_at=job.updated_at,
        expires_at=job.expires_at,
    )


def human3d_job_view(job: Human3DJob) -> Human3DJobView:
    expired = job.expires_at is not None and (
        job.expires_at.replace(tzinfo=timezone.utc)
        if job.expires_at.tzinfo is None
        else job.expires_at
    ) <= datetime.now(timezone.utc)
    return Human3DJobView(
        id=job.id,
        try_on_job_id=job.try_on_job_id,
        status=job.status,
        error=job.error_message,
        artifact_type="gaussian_splat" if job.status == "succeeded" else None,
        artifact_format=job.artifact_format,
        result_url=(
            f"/api/human3d/jobs/{job.id}/result"
            if job.status == "succeeded" and not expired
            else None
        ),
        created_at=job.created_at,
        updated_at=job.updated_at,
        expires_at=job.expires_at,
    )


def stored_reference_image(path: Path, display_name: str, reference_type: str):
    try:
        with path.open("rb") as handle:
            content = handle.read(settings.image_max_upload_bytes + 1)
    except OSError as error:
        raise HTTPException(
            status_code=409,
            detail=f"{REFERENCE_LABELS[reference_type]}商品圖片目前無法使用",
        ) from error
    return validate_image_bytes(
        content,
        filename=display_name,
        max_bytes=settings.image_max_upload_bytes,
        max_pixels=settings.image_max_pixels,
    )


def catalog_reference_image(cloth: Cloth, reference_type: str):
    return stored_reference_image(
        Path(cloth.image_path), cloth.product_display_name, reference_type
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


@router.get("/capabilities", response_model=TryOnCapabilities)
def capabilities() -> TryOnCapabilities:
    available, reason = tryon_client.health()
    return TryOnCapabilities(
        available=available,
        reason=reason,
        max_upload_bytes=settings.image_max_upload_bytes,
        max_image_pixels=settings.image_max_pixels,
    )


@router.post("/jobs", response_model=TryOnJobView, status_code=202)
async def create_job(
    person_image: UploadFile = File(...),
    upper_image: UploadFile | None = File(default=None),
    lower_image: UploadFile | None = File(default=None),
    overall_image: UploadFile | None = File(default=None),
    shoe_image: UploadFile | None = File(default=None),
    bag_image: UploadFile | None = File(default=None),
    upper_item_id: int | None = Form(default=None),
    lower_item_id: int | None = Form(default=None),
    overall_item_id: int | None = Form(default=None),
    shoe_item_id: int | None = Form(default=None),
    bag_item_id: int | None = Form(default=None),
    upper_wardrobe_item_id: int | None = Form(default=None),
    lower_wardrobe_item_id: int | None = Form(default=None),
    overall_wardrobe_item_id: int | None = Form(default=None),
    shoe_wardrobe_item_id: int | None = Form(default=None),
    bag_wardrobe_item_id: int | None = Form(default=None),
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
    item_ids = {
        "upper": upper_item_id,
        "lower": lower_item_id,
        "overall": overall_item_id,
        "shoe": shoe_item_id,
        "bag": bag_item_id,
    }
    wardrobe_item_ids = {
        "upper": upper_wardrobe_item_id,
        "lower": lower_wardrobe_item_id,
        "overall": overall_wardrobe_item_id,
        "shoe": shoe_wardrobe_item_id,
        "bag": bag_wardrobe_item_id,
    }
    duplicated_sources = [
        reference_type
        for reference_type in SUPPORTED_REFERENCE_TYPES
        if sum(
            source is not None
            for source in (
                uploads[reference_type],
                item_ids[reference_type],
                wardrobe_item_ids[reference_type],
            )
        ) > 1
    ]
    if duplicated_sources:
        label = REFERENCE_LABELS[duplicated_sources[0]]
        raise HTTPException(status_code=422, detail=f"{label}不可同時提供多個來源")
    present_types = [
        reference_type
        for reference_type in SUPPORTED_REFERENCE_TYPES
        if (
            uploads[reference_type] is not None
            or item_ids[reference_type] is not None
            or wardrobe_item_ids[reference_type] is not None
        )
    ]
    if not present_types:
        raise HTTPException(status_code=422, detail="至少需要一張參考圖片")
    if "overall" in present_types and (
        "upper" in present_types or "lower" in present_types
    ):
        raise HTTPException(status_code=422, detail="overall 不可與 upper 或 lower 同時使用")

    person = await validate_image(
        person_image,
        max_bytes=settings.image_max_upload_bytes,
        max_pixels=settings.image_max_pixels,
    )

    references: dict[str, tuple[bytes, str]] = {}
    stored_references: list[TryOnJobReference] = []
    for reference_type in present_types:
        item_id = item_ids[reference_type]
        wardrobe_item_id = wardrobe_item_ids[reference_type]
        upload = uploads[reference_type]
        if item_id is not None:
            cloth = db.get(Cloth, item_id)
            if cloth is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"找不到{REFERENCE_LABELS[reference_type]}商品",
                )
            if reference_type_for_cloth(cloth) != reference_type:
                raise HTTPException(
                    status_code=422,
                    detail=f"商品不適用於{REFERENCE_LABELS[reference_type]}槽位",
                )
            reference = catalog_reference_image(cloth, reference_type)
            stored_references.append(
                TryOnJobReference(
                    reference_type=reference_type,
                    source="catalog",
                    cloth_id=cloth.id,
                    display_name=cloth.product_display_name,
                    image_url=cloth.image_url,
                )
            )
        elif wardrobe_item_id is not None:
            wardrobe_item = db.get(UserWardrobeItem, wardrobe_item_id)
            if wardrobe_item is None or wardrobe_item.user_key != user_key:
                raise HTTPException(
                    status_code=404,
                    detail=f"找不到{REFERENCE_LABELS[reference_type]}衣櫃單品",
                )
            if WARDROBE_REFERENCE_TYPES.get(wardrobe_item.category) != reference_type:
                raise HTTPException(
                    status_code=422,
                    detail=f"衣櫃單品不適用於{REFERENCE_LABELS[reference_type]}槽位",
                )
            reference = stored_reference_image(
                Path(settings.wardrobe_dir) / wardrobe_item.stored_filename,
                wardrobe_item.name,
                reference_type,
            )
            stored_references.append(
                TryOnJobReference(
                    reference_type=reference_type,
                    source="wardrobe",
                    wardrobe_item_id=wardrobe_item.id,
                    display_name=wardrobe_item.name,
                    image_url=f"/wardrobe-media/{wardrobe_item.stored_filename}",
                )
            )
        else:
            if upload is None:
                continue
            reference = await validate_image(
                upload,
                max_bytes=settings.image_max_upload_bytes,
                max_pixels=settings.image_max_pixels,
            )
            stored_references.append(
                TryOnJobReference(
                    reference_type=reference_type,
                    source="upload",
                    display_name="自訂上傳",
                    image_url=None,
                )
            )
        references[reference_type] = (reference.content, reference.content_type)
    try:
        payload = await run_in_threadpool(
            tryon_client.create_job,
            person.content,
            person.content_type,
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
        references=stored_references,
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


@router.get("/history/{user_key}", response_model=TryOnHistoryView)
def get_history(
    user_key: str,
    limit: int = Query(default=20, ge=1, le=20),
    db: Session = Depends(get_db),
) -> TryOnHistoryView:
    jobs = list(
        db.scalars(
            select(TryOnJob)
            .where(
                TryOnJob.user_key == user_key,
                TryOnJob.history_hidden_at.is_(None),
            )
            .order_by(TryOnJob.created_at.desc(), TryOnJob.id.desc())
            .limit(limit)
        )
    )
    if not jobs:
        return TryOnHistoryView()

    job_ids = [job.id for job in jobs]
    latest_human3d: list[Human3DJob] = []
    seen_try_on_ids: set[uuid.UUID] = set()
    for human_job in db.scalars(
        select(Human3DJob)
        .where(Human3DJob.try_on_job_id.in_(job_ids))
        .order_by(Human3DJob.updated_at.desc(), Human3DJob.id.desc())
    ):
        if human_job.try_on_job_id in seen_try_on_ids:
            continue
        seen_try_on_ids.add(human_job.try_on_job_id)
        latest_human3d.append(human_job)
    return TryOnHistoryView(
        jobs=[job_view(job) for job in jobs],
        human3d_jobs=[human3d_job_view(job) for job in latest_human3d],
    )


@router.delete("/history/{user_key}", status_code=204)
def clear_history(user_key: str, db: Session = Depends(get_db)) -> Response:
    hidden_at = datetime.now(timezone.utc)
    for job in db.scalars(
        select(TryOnJob).where(
            TryOnJob.user_key == user_key,
            TryOnJob.history_hidden_at.is_(None),
        )
    ):
        job.history_hidden_at = hidden_at
    db.commit()
    return Response(status_code=204)


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
