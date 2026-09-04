"""Validate image uploads before they reach an AI model or external service."""

from dataclasses import dataclass
from io import BytesIO

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

IMAGE_TYPES = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}


@dataclass(frozen=True)
class ValidatedImage:
    """In-memory image content verified as safe for a configured use case."""

    content: bytes
    content_type: str
    image_format: str
    width: int
    height: int


async def validate_image(
    upload: UploadFile,
    *,
    max_bytes: int,
    max_pixels: int,
) -> ValidatedImage:
    """Read and validate JPEG, PNG, or WebP input without persisting it."""
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{upload.filename or '圖片'} 超過大小限制")
    if not content:
        raise HTTPException(status_code=422, detail="請上傳圖片")
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
        raise HTTPException(
            status_code=422,
            detail=f"{upload.filename or '檔案'} 不是有效圖片",
        ) from error
    if image_format not in IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="只支援 JPEG、PNG 或 WebP 圖片")
    if width * height > max_pixels:
        raise HTTPException(status_code=422, detail="圖片像素超過限制")
    return ValidatedImage(
        content=content,
        content_type=IMAGE_TYPES[image_format][1],
        image_format=image_format,
        width=width,
        height=height,
    )
