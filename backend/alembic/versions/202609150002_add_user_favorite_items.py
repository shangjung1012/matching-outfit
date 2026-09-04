"""add user favorite items

Revision ID: 202609150002
Revises: 202609150001
Create Date: 2026-09-15 00:02:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609150002"
down_revision: Union[str, None] = "202609150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_favorite_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("cloth_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["cloth_id"], ["clothes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_key", "cloth_id", name="uq_user_favorite_items_user_cloth"
        ),
    )
    op.create_index(
        "ix_user_favorite_items_user_created",
        "user_favorite_items",
        ["user_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_favorite_items_user_created", table_name="user_favorite_items"
    )
    op.drop_table("user_favorite_items")
