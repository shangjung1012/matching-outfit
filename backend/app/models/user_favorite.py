from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
)
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
    is_direct: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserFavoriteOutfit(Base):
    """An exact set of catalog items saved together as an outfit."""

    __tablename__ = "user_favorite_outfits"
    __table_args__ = (
        UniqueConstraint(
            "user_key", "item_signature", name="uq_user_favorite_outfits_user_signature"
        ),
        Index("ix_user_favorite_outfits_user_created", "user_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_key: Mapped[str] = mapped_column(String(120), nullable=False)
    item_signature: Mapped[str] = mapped_column(String(1200), nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserFavoriteOutfitItem(Base):
    """An ordered item within a saved outfit."""

    __tablename__ = "user_favorite_outfit_items"
    __table_args__ = (
        UniqueConstraint(
            "outfit_id", "favorite_item_id", name="uq_user_favorite_outfit_items_member"
        ),
        UniqueConstraint(
            "outfit_id", "position", name="uq_user_favorite_outfit_items_position"
        ),
        Index(
            "ix_user_favorite_outfit_items_favorite_item", "favorite_item_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    outfit_id: Mapped[int] = mapped_column(
        ForeignKey("user_favorite_outfits.id", ondelete="CASCADE"), nullable=False
    )
    favorite_item_id: Mapped[int] = mapped_column(
        ForeignKey("user_favorite_items.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
