"""add pending_reaction_count to user_summaries

Revision ID: 202609200003
Revises: 202609200002
Create Date: 2026-09-20 00:03:00
"""

from alembic import op
import sqlalchemy as sa


revision = "202609200003"
down_revision = "202609200002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_summaries",
        sa.Column(
            "pending_reaction_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_summaries", "pending_reaction_count")
