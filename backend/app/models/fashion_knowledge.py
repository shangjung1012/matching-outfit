from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.sql.sqltypes import DateTime

from app.models.base import Base


class FashionArticle(Base):
    __tablename__ = "fashion_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    source_name: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at = mapped_column(DateTime(timezone=True), nullable=False)
    language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    article_summary: Mapped[str] = mapped_column(Text)
    extraction_notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    extraction_model: Mapped[str] = mapped_column(String(160))
    extracted_at = mapped_column(DateTime(timezone=True), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    observations: Mapped[list["FashionObservation"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class FashionObservation(Base):
    __tablename__ = "fashion_observations"
    __table_args__ = (
        CheckConstraint(
            "signal_type IN ('timeless', 'current_trend', 'editorial_example')",
            name="ck_fashion_observations_signal_type",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_fashion_observations_confidence",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("fashion_articles.id", ondelete="CASCADE"), index=True
    )
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    audiences: Mapped[list[str]] = mapped_column(JSON, default=list)
    occasions: Mapped[list[str]] = mapped_column(JSON, default=list)
    climates: Mapped[list[str]] = mapped_column(JSON, default=list)
    seasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    times_of_day: Mapped[list[str]] = mapped_column(JSON, default=list)
    formalities: Mapped[list[str]] = mapped_column(JSON, default=list)
    activities: Mapped[list[str]] = mapped_column(JSON, default=list)
    styles: Mapped[list[str]] = mapped_column(JSON, default=list)
    garments: Mapped[list[str]] = mapped_column(JSON, default=list)
    colors: Mapped[list[str]] = mapped_column(JSON, default=list)
    materials: Mapped[list[str]] = mapped_column(JSON, default=list)
    silhouettes: Mapped[list[str]] = mapped_column(JSON, default=list)
    styling_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    avoid_when: Mapped[list[str]] = mapped_column(JSON, default=list)
    signal_type: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reviewed_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    article: Mapped[FashionArticle] = relationship(back_populates="observations")
