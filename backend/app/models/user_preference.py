from sqlalchemy import Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.sqltypes import DateTime

from app.models.base import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    favorite_colors: Mapped[list[str]] = mapped_column(JSON, default=list)
    disliked_colors: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_price_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_price_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_styles: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_usages: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
