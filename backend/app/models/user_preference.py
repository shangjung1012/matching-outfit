from sqlalchemy import (
    CheckConstraint,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.sqltypes import DateTime

from app.models.base import Base


class UserHardRule(Base):
    """A user's hard constraints - one row per user."""

    __tablename__ = "user_hard_rules"
    __table_args__ = (
        CheckConstraint(
            "price_min IS NULL OR price_min >= 0",
            name="ck_user_hard_rules_price_min_non_negative",
        ),
        CheckConstraint(
            "price_max IS NULL OR price_max >= 0",
            name="ck_user_hard_rules_price_max_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    # Price gate -> clothes.price BETWEEN price_min AND price_max
    price_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Attribute gates -> clothes.<column> NOT IN (...)  (values are normalised lower-case)
    avoid_colours: Mapped[list[str]] = mapped_column(JSON, default=list)          # clothes.base_colour
    avoid_article_types: Mapped[list[str]] = mapped_column(JSON, default=list)    # clothes.article_type
    avoid_master_categories: Mapped[list[str]] = mapped_column(JSON, default=list)  # clothes.master_category

    # Free-text: lightweight soft-explicit context / a gate the planner must honour verbatim
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UserStylePreference(Base):
    """Soft, weighted taste - both user-authored (``explicit``) and learned from
    behaviour then confirmed (``implicit``). Many rows per user.
    """

    __tablename__ = "user_style_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_key",
            "axis",
            "value",
            "zone",
            "polarity",
            name="uq_user_style_preference_slot",
        ),
        CheckConstraint(
            "polarity IN ('prefer', 'avoid')",
            name="ck_user_style_preferences_polarity",
        ),
        CheckConstraint(
            "source IN ('explicit', 'implicit')",
            name="ck_user_style_preferences_source",
        ),
        CheckConstraint(
            "weight >= 0 AND weight <= 1",
            name="ck_user_style_preferences_weight",
        ),
        CheckConstraint(
            "zone IN ('upper_body', 'lower_body', 'one_piece', 'accessory', 'any')",
            name="ck_user_style_preferences_zone",
        ),
        Index("ix_user_style_preferences_lookup", "user_key", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_key: Mapped[str] = mapped_column(String(120), index=True)

    # --- what the taste is (shared vocabulary with FashionObservation) ---
    # axis: "style" | "color" | "silhouette" | "material" | "article_type"
    #       | "pattern" | "length" | "fit" | "brand"
    axis: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(500))  # term or a confirmed outfit-memory sentence
    zone: Mapped[str] = mapped_column(String(16), default="any")  # which garment slot this applies to ("any" = whole outfit)
    polarity: Mapped[str] = mapped_column(String(8), default="prefer")  # "prefer" | "avoid"
    weight: Mapped[float] = mapped_column(Float, default=0.3)  # 0..1, same scale as FashionObservation.confidence

    # --- where it came from ---
    source: Mapped[str] = mapped_column(String(16), default="explicit")  # "explicit" (settings UI) | "implicit" (learned + confirmed)
    origin: Mapped[str | None] = mapped_column(String(255), nullable=True)  # "settings" | query text | liked-outfit id
    origin_item_ids: Mapped[list[str]] = mapped_column(JSON, default=list)  # catalog ids of the outfit it was promoted from

    # --- context scoping (same axes as FashionObservation; empty list = always applies) ---
    context_occasions: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_seasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_climates: Mapped[list[str]] = mapped_column(JSON, default=list)

    # --- lifecycle (user-managed pruning replaces time-decay) ---
    is_active: Mapped[bool] = mapped_column(default=True)
    confirmed_at = mapped_column(DateTime(timezone=True), nullable=True)   # when the user pressed "add to preferences"
    last_applied_at = mapped_column(DateTime(timezone=True), nullable=True)  # last time it influenced a recommendation

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
