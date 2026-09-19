from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user_wardrobe import UserWardrobeItem
from app.schemas.wardrobe import WardrobeFavoriteUpdate, WardrobeItemView
from app.services.image_inputs.validation import IMAGE_TYPES, validate_image


router = APIRouter(prefix="/wardrobe", tags=["wardrobe"])
WARDROBE_CATEGORIES = {"upper_body", "lower_body", "shoes"}


def item_view(item: UserWardrobeItem) -> WardrobeItemView:
    return WardrobeItemView(
        id=item.id,
        name=item.name,
        category=item.category,
        image_url=f"/wardrobe-media/{item.stored_filename}",
        original_filename=item.original_filename,
        is_favorite=item.is_favorite,
        created_at=item.created_at,
    )


@router.get("/{user_key}", response_model=list[WardrobeItemView])
def list_wardrobe(
    user_key: str,
    category: str | None = Query(default=None),
    favorites_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[WardrobeItemView]:
    if category is not None and category not in WARDROBE_CATEGORIES:
        raise HTTPException(status_code=422, detail="不支援的衣櫃分類")
    statement = select(UserWardrobeItem).where(UserWardrobeItem.user_key == user_key)
    if category is not None:
        statement = statement.where(UserWardrobeItem.category == category)
    if favorites_only:
        statement = statement.where(UserWardrobeItem.is_favorite.is_(True))
    rows = db.scalars(statement.order_by(UserWardrobeItem.created_at.desc())).all()
    return [item_view(row) for row in rows]


@router.post(
    "/{user_key}", response_model=WardrobeItemView, status_code=status.HTTP_201_CREATED
)
async def upload_wardrobe_item(
    user_key: str,
    category: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> WardrobeItemView:
    if category not in WARDROBE_CATEGORIES:
        raise HTTPException(status_code=422, detail="分類必須是上裝、下裝或鞋子")
    validated = await validate_image(
        image,
        max_bytes=settings.image_max_upload_bytes,
        max_pixels=settings.image_max_pixels,
    )
    original_filename = Path(image.filename or "未命名單品").name
    name = Path(original_filename).stem.strip() or "未命名單品"
    suffix = IMAGE_TYPES[validated.image_format][0]
    stored_filename = f"{uuid4().hex}{suffix}"
    wardrobe_dir = Path(settings.wardrobe_dir)
    wardrobe_dir.mkdir(parents=True, exist_ok=True)
    target = wardrobe_dir / stored_filename
    target.write_bytes(validated.content)

    row = UserWardrobeItem(
        user_key=user_key,
        name=name[:200],
        category=category,
        stored_filename=stored_filename,
        original_filename=original_filename[:255],
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise
    return item_view(row)


@router.patch("/{user_key}/{item_id}/favorite", response_model=WardrobeItemView)
def update_wardrobe_favorite(
    user_key: str,
    item_id: int,
    payload: WardrobeFavoriteUpdate,
    db: Session = Depends(get_db),
) -> WardrobeItemView:
    row = db.get(UserWardrobeItem, item_id)
    if row is None or row.user_key != user_key:
        raise HTTPException(status_code=404, detail="找不到衣櫃單品")
    row.is_favorite = payload.is_favorite
    db.commit()
    db.refresh(row)
    return item_view(row)


@router.delete("/{user_key}/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wardrobe_item(
    user_key: str, item_id: int, db: Session = Depends(get_db)
) -> None:
    row = db.get(UserWardrobeItem, item_id)
    if row is None or row.user_key != user_key:
        raise HTTPException(status_code=404, detail="找不到衣櫃單品")
    stored_filename = row.stored_filename
    db.delete(row)
    db.commit()
    (Path(settings.wardrobe_dir) / stored_filename).unlink(missing_ok=True)

