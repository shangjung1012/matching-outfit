from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class UserFavoriteItem(Base):
    """A catalog item saved by a user."""

    __tablename__ = "user_favorite_items"
    __table_args__ = (
        UniqueConstraint(
            "user_key", "cloth_id", name="uq_user_favorite_items_user_cloth"
        ),
        Index(
            "ix_user_favorite_items_user_created", "user_key", "created_at"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_key: Mapped[str] = mapped_column(String(120), nullable=False)
    cloth_id: Mapped[int] = mapped_column(
        ForeignKey("clothes.id", ondelete="CASCADE"), nullable=False
    )
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
