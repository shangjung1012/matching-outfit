from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from pydantic import BaseModel


JobStatus = Literal["queued", "running", "succeeded", "failed"]


class JobManifest(BaseModel):
    id: uuid.UUID
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    error: str | None = None
    input_object_key: str | None = None
    result_object_key: str | None = None
    artifact_type: str | None = None
    artifact_format: str | None = None
    peak_gpu_memory_bytes: int | None = None


class JobView(BaseModel):
    id: uuid.UUID
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    error: str | None = None
    artifact_type: str | None = None
    artifact_format: str | None = None
    result_url: str | None = None
    peak_gpu_memory_bytes: int | None = None
