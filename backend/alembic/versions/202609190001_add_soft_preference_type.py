"""add prefer/avoid direction to soft preferences

Revision ID: 202609190001
Revises: 202609180001
Create Date: 2026-09-19 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "202609190001"
down_revision = "202609180001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_style_preferences",
        sa.Column(
            "preference_type",
            sa.String(length=8),
            nullable=False,
            server_default="prefer",
        ),
    )
    op.create_check_constraint(
        "ck_user_style_preferences_preference_type",
        "user_style_preferences",
        "preference_type IN ('prefer', 'avoid')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_user_style_preferences_preference_type",
        "user_style_preferences",
        type_="check",
    )
    op.drop_column("user_style_preferences", "preference_type")
