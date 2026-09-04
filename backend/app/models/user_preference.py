from sqlalchemy import (
    CheckConstraint,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
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
        CheckConstraint(
            "gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'prefer_not_to_say')",
            name="ck_user_hard_rules_gender",
        ),
        CheckConstraint(
            "age IS NULL OR (age >= 1 AND age <= 120)",
            name="ck_user_hard_rules_age",
        ),
        CheckConstraint(
            "height_cm IS NULL OR (height_cm >= 50 AND height_cm <= 250)",
            name="ck_user_hard_rules_height_cm",
        ),
        CheckConstraint(
            "weight_kg IS NULL OR (weight_kg >= 10 AND weight_kg <= 400)",
            name="ck_user_hard_rules_weight_kg",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    gender: Mapped[str | None] = mapped_column(String(24), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

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
    """Context-scoped preference sentences confirmed by the user."""

    __tablename__ = "user_style_preferences"
    __table_args__ = (
        CheckConstraint(
            "source IN ('explicit', 'implicit')",
            name="ck_user_style_preferences_source",
        ),
        Index("ix_user_style_preferences_lookup", "user_key", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_key: Mapped[str] = mapped_column(String(120), index=True)

    preference_text: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(16), default="explicit")
    origin_item_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_occasions: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_times: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_situations: Mapped[list[str]] = mapped_column(JSON, default=list)

    # --- lifecycle (user-managed pruning replaces time-decay) ---
    is_active: Mapped[bool] = mapped_column(default=True)
    confirmed_at = mapped_column(DateTime(timezone=True), nullable=True)   # when the user pressed "add to preferences"
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
