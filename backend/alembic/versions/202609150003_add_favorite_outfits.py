"""add favorite outfit relationships

Revision ID: 202609150003
Revises: 202609150002
Create Date: 2026-09-15 00:03:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609150003"
down_revision: Union[str, None] = "202609150002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_favorite_items",
        sa.Column(
            "is_direct",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.alter_column(
        "user_favorite_items", "is_direct", server_default=sa.false()
    )

    op.create_table(
        "user_favorite_outfits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("item_signature", sa.String(length=1200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_key",
            "item_signature",
            name="uq_user_favorite_outfits_user_signature",
        ),
    )
    op.create_index(
        "ix_user_favorite_outfits_user_created",
        "user_favorite_outfits",
        ["user_key", "created_at"],
    )
    op.create_table(
        "user_favorite_outfit_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("outfit_id", sa.Integer(), nullable=False),
        sa.Column("favorite_item_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["favorite_item_id"],
            ["user_favorite_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outfit_id"], ["user_favorite_outfits.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "outfit_id",
            "favorite_item_id",
            name="uq_user_favorite_outfit_items_member",
        ),
        sa.UniqueConstraint(
            "outfit_id",
            "position",
            name="uq_user_favorite_outfit_items_position",
        ),
    )
    op.create_index(
        "ix_user_favorite_outfit_items_favorite_item",
        "user_favorite_outfit_items",
        ["favorite_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_favorite_outfit_items_favorite_item",
        table_name="user_favorite_outfit_items",
    )
    op.drop_table("user_favorite_outfit_items")
    op.drop_index(
        "ix_user_favorite_outfits_user_created", table_name="user_favorite_outfits"
    )
    op.drop_table("user_favorite_outfits")
    op.drop_column("user_favorite_items", "is_direct")
