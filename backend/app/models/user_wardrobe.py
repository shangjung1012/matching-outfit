from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, false
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class UserWardrobeItem(Base):
    """A user-owned garment image, separate from the product catalog."""

    __tablename__ = "user_wardrobe_items"
    __table_args__ = (
        CheckConstraint(
            "category IN ('upper_body', 'lower_body', 'one_piece', 'shoes', 'bags')",
            name="ck_user_wardrobe_items_category",
        ),
        Index("ix_user_wardrobe_items_user_created", "user_key", "created_at"),
        Index("ix_user_wardrobe_items_user_favorite", "user_key", "is_favorite"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    is_favorite: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
