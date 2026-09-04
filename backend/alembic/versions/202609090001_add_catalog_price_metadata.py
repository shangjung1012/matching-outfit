"""add catalog price metadata

Revision ID: 202609090001
Revises: 202609040001
Create Date: 2026-09-09 22:05:19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609090001"
down_revision: Union[str, None] = "202609040001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clothes", sa.Column("original_price", sa.Integer(), nullable=True))
    op.add_column("clothes", sa.Column("discounted_price", sa.Integer(), nullable=True))
    op.add_column(
        "clothes",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
    )
    op.add_column("clothes", sa.Column("brand_name", sa.String(length=160), nullable=True))
    op.add_column("clothes", sa.Column("age_group", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("clothes", "age_group")
    op.drop_column("clothes", "brand_name")
    op.drop_column("clothes", "currency")
    op.drop_column("clothes", "discounted_price")
    op.drop_column("clothes", "original_price")
