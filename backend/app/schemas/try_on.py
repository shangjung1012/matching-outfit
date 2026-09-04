import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TryOnReferenceType = Literal["upper", "lower", "overall", "shoe", "bag"]
TryOnJobStatus = Literal["queued", "running", "succeeded", "failed"]

SUPPORTED_REFERENCE_TYPES: tuple[TryOnReferenceType, ...] = (
    "upper",
    "lower",
    "overall",
    "shoe",
    "bag",
)


class TryOnCapabilities(BaseModel):
    available: bool
    reason: str | None = None
    supported_reference_types: list[TryOnReferenceType] = Field(
        default_factory=lambda: list(SUPPORTED_REFERENCE_TYPES)
    )
    max_upload_bytes: int
    max_image_pixels: int


class TryOnJobView(BaseModel):
    id: uuid.UUID
    status: TryOnJobStatus
    reference_types: list[TryOnReferenceType]
    error: str | None = None
    result_url: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
