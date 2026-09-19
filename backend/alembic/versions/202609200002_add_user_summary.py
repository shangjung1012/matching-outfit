"""add user summary (personal memory)

Revision ID: 202609200002
Revises: 202609200001
Create Date: 2026-09-20 00:02:00
"""

from alembic import op
import sqlalchemy as sa


revision = "202609200002"
down_revision = "202609200001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_summaries",
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("user_key"),
    )


def downgrade() -> None:
    op.drop_table("user_summaries")
