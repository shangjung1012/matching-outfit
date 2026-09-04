"""initial schema

Revision ID: 202609040001
Revises:
Create Date: 2026-09-04 20:14:37
"""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa

revision: str = "202609040001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "clothes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_item_id", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(length=40), nullable=True),
        sa.Column("master_category", sa.String(length=80), nullable=True),
        sa.Column("sub_category", sa.String(length=80), nullable=True),
        sa.Column("article_type", sa.String(length=120), nullable=True),
        sa.Column("base_colour", sa.String(length=80), nullable=True),
        sa.Column("season", sa.String(length=40), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("usage", sa.String(length=80), nullable=True),
        sa.Column("product_display_name", sa.String(length=255), nullable=False),
        sa.Column("garment_zone", sa.String(length=24), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("embedding", Vector(dim=512), nullable=True),
        sa.Column("embedding_model", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_item_id"),
        sa.CheckConstraint(
            "garment_zone IN ('upper_body', 'lower_body', 'one_piece', 'accessory', 'other')",
            name="ck_clothes_garment_zone",
        ),
        sa.CheckConstraint("price >= 0", name="ck_clothes_price_non_negative"),
    )
    op.create_index("ix_clothes_source_item_id", "clothes", ["source_item_id"])
    op.create_index("ix_clothes_garment_zone", "clothes", ["garment_zone"])
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("favorite_colors", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("disliked_colors", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("preferred_price_min", sa.Integer(), nullable=True),
        sa.Column("preferred_price_max", sa.Integer(), nullable=True),
        sa.Column("preferred_styles", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("preferred_categories", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("preferred_usages", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("favorite_article_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("disliked_article_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_key"),
    )
    op.create_index("ix_user_preferences_user_key", "user_preferences", ["user_key"])
    op.create_table(
        "fashion_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("rule_type", sa.String(length=80), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=160), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fashion_rules_rule_type", "fashion_rules", ["rule_type"])
    op.create_index("ix_fashion_rules_is_active", "fashion_rules", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_fashion_rules_is_active", table_name="fashion_rules")
    op.drop_index("ix_fashion_rules_rule_type", table_name="fashion_rules")
    op.drop_table("fashion_rules")
    op.drop_index("ix_user_preferences_user_key", table_name="user_preferences")
    op.drop_table("user_preferences")
    op.drop_index("ix_clothes_source_item_id", table_name="clothes")
    op.drop_index("ix_clothes_garment_zone", table_name="clothes")
    op.drop_table("clothes")
