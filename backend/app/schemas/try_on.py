import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

TryOnClothType = Literal["upper", "lower", "overall"]
TryOnJobStatus = Literal["queued", "running", "succeeded", "failed"]


class TryOnCapabilities(BaseModel):
    available: bool
    reason: str | None = None
    supported_cloth_types: list[TryOnClothType] = ["upper", "lower", "overall"]
    max_upload_bytes: int


class TryOnJobView(BaseModel):
    id: uuid.UUID
    status: TryOnJobStatus
    cloth_type: TryOnClothType
    error: str | None = None
    result_url: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
