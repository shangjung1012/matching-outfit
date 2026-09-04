"""add user profile fields

Revision ID: 202609050004
Revises: 202609050003
Create Date: 2026-09-05 23:14:19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609050004"
down_revision: Union[str, None] = "202609050003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_hard_rules", sa.Column("gender", sa.String(24), nullable=True))
    op.add_column("user_hard_rules", sa.Column("age", sa.Integer(), nullable=True))
    op.add_column("user_hard_rules", sa.Column("height_cm", sa.Float(), nullable=True))
    op.add_column("user_hard_rules", sa.Column("weight_kg", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_user_hard_rules_gender",
        "user_hard_rules",
        "gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'prefer_not_to_say')",
    )
    op.create_check_constraint(
        "ck_user_hard_rules_age",
        "user_hard_rules",
        "age IS NULL OR (age >= 1 AND age <= 120)",
    )
    op.create_check_constraint(
        "ck_user_hard_rules_height_cm",
        "user_hard_rules",
        "height_cm IS NULL OR (height_cm >= 50 AND height_cm <= 250)",
    )
    op.create_check_constraint(
        "ck_user_hard_rules_weight_kg",
        "user_hard_rules",
        "weight_kg IS NULL OR (weight_kg >= 10 AND weight_kg <= 400)",
    )


def downgrade() -> None:
    for constraint in (
        "ck_user_hard_rules_weight_kg",
        "ck_user_hard_rules_height_cm",
        "ck_user_hard_rules_age",
        "ck_user_hard_rules_gender",
    ):
        op.drop_constraint(constraint, "user_hard_rules", type_="check")
    for column in ("weight_kg", "height_cm", "age", "gender"):
        op.drop_column("user_hard_rules", column)
