import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.human3d import Human3DJobView
from app.schemas.workflow import CatalogItem
from app.schemas.wardrobe import WardrobeItemView

TryOnReferenceType = Literal["upper", "lower", "overall", "shoe", "bag"]
TryOnJobStatus = Literal["queued", "running", "succeeded", "failed"]
TryOnReferenceSource = Literal["catalog", "wardrobe", "upload"]

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


class TryOnJobReferenceView(BaseModel):
    reference_type: TryOnReferenceType
    source: TryOnReferenceSource
    display_name: str
    image_url: str | None = None
    catalog_item: CatalogItem | None = None
    wardrobe_item: WardrobeItemView | None = None


class TryOnJobView(BaseModel):
    id: uuid.UUID
    status: TryOnJobStatus
    reference_types: list[TryOnReferenceType]
    references: list[TryOnJobReferenceView] = Field(default_factory=list)
    error: str | None = None
    result_url: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None


class TryOnHistoryView(BaseModel):
    jobs: list[TryOnJobView] = Field(default_factory=list)
    human3d_jobs: list[Human3DJobView] = Field(default_factory=list)
