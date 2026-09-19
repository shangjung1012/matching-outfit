import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TryOnJob(Base):
    __tablename__ = "try_on_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_try_on_jobs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    reference_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)
    remote_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    history_hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    references: Mapped[list["TryOnJobReference"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="TryOnJobReference.id",
        lazy="selectin",
    )


class TryOnJobReference(Base):
    __tablename__ = "try_on_job_references"
    __table_args__ = (
        CheckConstraint(
            "reference_type IN ('upper', 'lower', 'overall', 'shoe', 'bag')",
            name="ck_try_on_job_references_type",
        ),
        CheckConstraint(
            "source IN ('catalog', 'wardrobe', 'upload')",
            name="ck_try_on_job_references_source",
        ),
        UniqueConstraint(
            "try_on_job_id",
            "reference_type",
            name="uq_try_on_job_references_job_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    try_on_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("try_on_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    cloth_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("clothes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    wardrobe_item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_wardrobe_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    job: Mapped[TryOnJob] = relationship(back_populates="references")
    cloth: Mapped["Cloth | None"] = relationship(lazy="selectin")
    wardrobe_item: Mapped["UserWardrobeItem | None"] = relationship(lazy="selectin")


from app.models.cloth import Cloth  # noqa: E402  # imported after model declarations
from app.models.user_wardrobe import UserWardrobeItem  # noqa: E402
