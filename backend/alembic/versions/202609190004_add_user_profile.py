"""add user profile login state

Revision ID: 202609190004
Revises: 202609190003
Create Date: 2026-09-19 13:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "202609190004"
down_revision = "202609190003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("do_test", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("user_key"),
    )


def downgrade() -> None:
    op.drop_table("user_profile")
