from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.sqltypes import DateTime

from app.models.base import Base


class UserSummary(Base):
    """A free-form paragraph of durable dressing habits/preferences, rewritten
    wholesale by the LLM after each completed recommendation session."""

    __tablename__ = "user_summaries"

    user_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
