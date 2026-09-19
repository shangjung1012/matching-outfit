from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.sqltypes import DateTime

from app.models.base import Base


class UserProfile(Base):
    """Minimal account-level state for a user key used by the application."""

    __tablename__ = "user_profile"

    user_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    do_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
