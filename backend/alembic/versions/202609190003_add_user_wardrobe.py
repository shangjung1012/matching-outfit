"""add user wardrobe items

Revision ID: 202609190003
Revises: 202609190002
Create Date: 2026-09-19 22:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "202609190003"
down_revision = "202609190002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_wardrobe_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("stored_filename", sa.String(length=100), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("is_favorite", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('upper_body', 'lower_body', 'shoes')",
            name="ck_user_wardrobe_items_category",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )
    op.create_index("ix_user_wardrobe_items_user_key", "user_wardrobe_items", ["user_key"])
    op.create_index(
        "ix_user_wardrobe_items_user_created",
        "user_wardrobe_items",
        ["user_key", "created_at"],
    )
    op.create_index(
        "ix_user_wardrobe_items_user_favorite",
        "user_wardrobe_items",
        ["user_key", "is_favorite"],
    )


def downgrade() -> None:
    op.drop_table("user_wardrobe_items")

