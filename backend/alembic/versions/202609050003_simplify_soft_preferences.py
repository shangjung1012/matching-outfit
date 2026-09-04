"""simplify soft preferences to context-scoped sentences

Revision ID: 202609050003
Revises: 202609050002
Create Date: 2026-09-05 17:03:05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609050003"
down_revision: Union[str, None] = "202609050002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM user_style_preferences WHERE polarity = 'avoid'")
    op.execute(
        """
        UPDATE user_style_preferences
        SET value = '使用者偏好 ' || axis || ': ' || value
        WHERE origin IS DISTINCT FROM 'liked-outfit-sentence'
        """
    )
    op.drop_constraint(
        "uq_user_style_preference_slot", "user_style_preferences", type_="unique"
    )
    op.drop_constraint(
        "ck_user_style_preferences_polarity", "user_style_preferences", type_="check"
    )
    op.drop_constraint(
        "ck_user_style_preferences_weight", "user_style_preferences", type_="check"
    )
    op.drop_constraint(
        "ck_user_style_preferences_zone", "user_style_preferences", type_="check"
    )
    op.alter_column(
        "user_style_preferences", "value", new_column_name="preference_text"
    )
    op.alter_column(
        "user_style_preferences", "context_seasons", new_column_name="context_times"
    )
    op.alter_column(
        "user_style_preferences", "context_climates", new_column_name="context_situations"
    )
    for column in ("axis", "zone", "polarity", "weight", "origin", "last_applied_at"):
        op.drop_column("user_style_preferences", column)


def downgrade() -> None:
    op.add_column(
        "user_style_preferences",
        sa.Column("axis", sa.String(length=32), nullable=False, server_default="style"),
    )
    op.add_column(
        "user_style_preferences",
        sa.Column("zone", sa.String(length=16), nullable=False, server_default="any"),
    )
    op.add_column(
        "user_style_preferences",
        sa.Column("polarity", sa.String(length=8), nullable=False, server_default="prefer"),
    )
    op.add_column(
        "user_style_preferences",
        sa.Column("weight", sa.Float(), nullable=False, server_default="0.3"),
    )
    op.add_column(
        "user_style_preferences", sa.Column("origin", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "user_style_preferences",
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column(
        "user_style_preferences", "preference_text", new_column_name="value"
    )
    op.alter_column(
        "user_style_preferences", "context_times", new_column_name="context_seasons"
    )
    op.alter_column(
        "user_style_preferences", "context_situations", new_column_name="context_climates"
    )
    op.create_check_constraint(
        "ck_user_style_preferences_polarity",
        "user_style_preferences",
        "polarity IN ('prefer', 'avoid')",
    )
    op.create_check_constraint(
        "ck_user_style_preferences_weight",
        "user_style_preferences",
        "weight >= 0 AND weight <= 1",
    )
    op.create_check_constraint(
        "ck_user_style_preferences_zone",
        "user_style_preferences",
        "zone IN ('upper_body', 'lower_body', 'one_piece', 'accessory', 'any')",
    )
    op.create_unique_constraint(
        "uq_user_style_preference_slot",
        "user_style_preferences",
        ["user_key", "axis", "value", "zone", "polarity"],
    )
