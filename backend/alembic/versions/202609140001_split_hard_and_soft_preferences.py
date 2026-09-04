"""split user preferences into hard rules and soft style rows

Revision ID: 202609140001
Revises: 202609120001
Create Date: 2026-09-14 23:19:26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609140001"
down_revision: Union[str, None] = "202609120001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DROPPED_SOFT_COLUMNS = (
    "favorite_colors",
    "disliked_colors",
    "preferred_price_min",
    "preferred_price_max",
    "preferred_styles",
    "preferred_categories",
    "preferred_usages",
    "favorite_article_types",
    "disliked_article_types",
)
NEW_HARD_LIST_COLUMNS = (
    "avoid_colours",
    "avoid_article_types",
    "avoid_master_categories",
    "exclude_zones",
)


def upgrade() -> None:
    # 1. user_preferences -> user_hard_rules (hard gates only)
    op.rename_table("user_preferences", "user_hard_rules")
    op.execute("ALTER INDEX ix_user_preferences_user_key RENAME TO ix_user_hard_rules_user_key")

    op.add_column("user_hard_rules", sa.Column("price_min", sa.Integer(), nullable=True))
    op.add_column("user_hard_rules", sa.Column("price_max", sa.Integer(), nullable=True))
    for name in NEW_HARD_LIST_COLUMNS:
        op.add_column(
            "user_hard_rules",
            sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        )
    op.add_column("user_hard_rules", sa.Column("required_gender", sa.String(length=40), nullable=True))
    op.add_column("user_hard_rules", sa.Column("size_requirement", sa.String(length=40), nullable=True))
    op.create_check_constraint(
        "ck_user_hard_rules_price_min_non_negative",
        "user_hard_rules",
        "price_min IS NULL OR price_min >= 0",
    )
    op.create_check_constraint(
        "ck_user_hard_rules_price_max_non_negative",
        "user_hard_rules",
        "price_max IS NULL OR price_max >= 0",
    )
    for name in DROPPED_SOFT_COLUMNS:
        op.drop_column("user_hard_rules", name)

    # 2. new table for soft, weighted taste
    op.create_table(
        "user_style_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("axis", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("zone", sa.String(length=16), nullable=False, server_default="any"),
        sa.Column("polarity", sa.String(length=8), nullable=False, server_default="prefer"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="explicit"),
        sa.Column("origin", sa.String(length=255), nullable=True),
        sa.Column("origin_item_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("context_occasions", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("context_seasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("context_climates", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("polarity IN ('prefer', 'avoid')", name="ck_user_style_preferences_polarity"),
        sa.CheckConstraint("source IN ('explicit', 'implicit')", name="ck_user_style_preferences_source"),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_user_style_preferences_weight"),
        sa.CheckConstraint(
            "zone IN ('upper_body', 'lower_body', 'one_piece', 'accessory', 'any')",
            name="ck_user_style_preferences_zone",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_key", "axis", "value", "zone", "polarity", name="uq_user_style_preference_slot"
        ),
    )
    op.create_index(
        "ix_user_style_preferences_lookup",
        "user_style_preferences",
        ["user_key", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_style_preferences_lookup", table_name="user_style_preferences")
    op.drop_table("user_style_preferences")

    for name in (
        "favorite_colors",
        "disliked_colors",
        "preferred_styles",
        "preferred_categories",
        "preferred_usages",
        "favorite_article_types",
        "disliked_article_types",
    ):
        op.add_column(
            "user_hard_rules",
            sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        )
    op.add_column("user_hard_rules", sa.Column("preferred_price_min", sa.Integer(), nullable=True))
    op.add_column("user_hard_rules", sa.Column("preferred_price_max", sa.Integer(), nullable=True))

    op.drop_constraint("ck_user_hard_rules_price_max_non_negative", "user_hard_rules")
    op.drop_constraint("ck_user_hard_rules_price_min_non_negative", "user_hard_rules")
    for name in (
        "size_requirement",
        "required_gender",
        *reversed(NEW_HARD_LIST_COLUMNS),
        "price_max",
        "price_min",
    ):
        op.drop_column("user_hard_rules", name)

    op.execute("ALTER INDEX ix_user_hard_rules_user_key RENAME TO ix_user_preferences_user_key")
    op.rename_table("user_hard_rules", "user_preferences")
