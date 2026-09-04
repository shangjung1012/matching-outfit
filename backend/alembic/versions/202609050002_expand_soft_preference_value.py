"""expand soft preference value for outfit-memory sentences

Revision ID: 202609050002
Revises: 202609050001
Create Date: 2026-09-05 22:12:10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609050002"
down_revision: Union[str, None] = "202609050001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "user_style_preferences",
        "value",
        existing_type=sa.String(length=80),
        type_=sa.String(length=500),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "user_style_preferences",
        "value",
        existing_type=sa.String(length=500),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
