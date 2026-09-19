from datetime import datetime
from typing import Literal
import uuid

from pydantic import BaseModel, Field


Human3DJobStatus = Literal["queued", "running", "succeeded", "failed"]


class Human3DCapabilities(BaseModel):
    available: bool
    reason: str | None = None
    artifact_formats: list[str] = Field(default_factory=lambda: ["ply"])


class Human3DCreateRequest(BaseModel):
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)


class Human3DJobView(BaseModel):
    id: uuid.UUID
    try_on_job_id: uuid.UUID
    status: Human3DJobStatus
    error: str | None = None
    artifact_type: str | None = None
    artifact_format: str | None = None
    result_url: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
