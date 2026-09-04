"""remove unused hard-rule columns

Revision ID: 202609050001
Revises: 202609140001
Create Date: 2026-09-05 19:24:38
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609050001"
down_revision: Union[str, None] = "202609140001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("user_hard_rules", "required_gender")
    op.drop_column("user_hard_rules", "exclude_zones")
    op.drop_column("user_hard_rules", "size_requirement")


def downgrade() -> None:
    op.add_column("user_hard_rules", sa.Column("size_requirement", sa.String(length=40), nullable=True))
    op.add_column("user_hard_rules", sa.Column("required_gender", sa.String(length=40), nullable=True))
    op.add_column(
        "user_hard_rules",
        sa.Column(
            "exclude_zones",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
