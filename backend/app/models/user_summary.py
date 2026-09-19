from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.sqltypes import DateTime

from app.models.base import Base


class UserSummary(Base):
    """A free-form paragraph of durable dressing habits/preferences, rewritten
    wholesale by the LLM after each completed recommendation session or after
    enough outfit reactions (likes/dislikes) accumulate."""

    __tablename__ = "user_summaries"

    user_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Outfit reactions since the last rewrite; reset to 0 once it triggers one
    # (see settings.user_summary_reaction_batch_size).
    pending_reaction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # No onupdate=func.now() here on purpose: this must reflect when
    # summary_text itself last changed, not every row touch (e.g. bumping
    # pending_reaction_count alone must not move it) - callers that change
    # summary_text set this explicitly.
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
