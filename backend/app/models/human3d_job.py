import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Human3DJob(Base):
    __tablename__ = "human3d_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_human3d_jobs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    try_on_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("try_on_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    remote_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    artifact_format: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
