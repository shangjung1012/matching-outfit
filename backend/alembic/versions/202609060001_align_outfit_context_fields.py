"""align outfit context fields

Revision ID: 202609060001
Revises: 202609050004
Create Date: 2026-09-06 18:01:43
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609060001"
down_revision: Union[str, None] = "202609050004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONTEXT_FIELDS = (
    "occasions",
    "seasons",
    "times_of_day",
    "climates",
    "formalities",
    "activities",
    "styles",
)


def json_list_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.JSON(),
        nullable=False,
        server_default=sa.text("'[]'::json"),
    )


def upgrade() -> None:
    for field in ("times_of_day", "formalities", "activities"):
        op.add_column("fashion_observations", json_list_column(field))

    for field in CONTEXT_FIELDS:
        op.add_column("user_style_preferences", json_list_column(field))
    op.execute(
        "UPDATE user_style_preferences "
        "SET occasions = context_occasions, "
        "times_of_day = context_times, activities = context_situations"
    )
    for field in ("context_situations", "context_times", "context_occasions"):
        op.drop_column("user_style_preferences", field)


def downgrade() -> None:
    for field in ("context_occasions", "context_times", "context_situations"):
        op.add_column("user_style_preferences", json_list_column(field))
    op.execute(
        "UPDATE user_style_preferences "
        "SET context_occasions = occasions, "
        "context_times = times_of_day, context_situations = activities"
    )
    for field in reversed(CONTEXT_FIELDS):
        op.drop_column("user_style_preferences", field)

    for field in ("activities", "formalities", "times_of_day"):
        op.drop_column("fashion_observations", field)
