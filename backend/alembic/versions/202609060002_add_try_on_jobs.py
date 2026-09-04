"""add virtual try-on jobs

Revision ID: 202609060002
Revises: 202609040001
Create Date: 2026-09-06 15:42:08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609060002"
down_revision: Union[str, None] = "202609040001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "try_on_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("cloth_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("person_object_key", sa.String(length=500), nullable=True),
        sa.Column("cloth_object_key", sa.String(length=500), nullable=True),
        sa.Column("result_object_key", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "cloth_type IN ('upper', 'lower', 'overall')",
            name="ck_try_on_jobs_cloth_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_try_on_jobs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_try_on_jobs_user_key", "try_on_jobs", ["user_key"])
    op.create_index("ix_try_on_jobs_status", "try_on_jobs", ["status"])
    op.create_index("ix_try_on_jobs_expires_at", "try_on_jobs", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_try_on_jobs_expires_at", table_name="try_on_jobs")
    op.drop_index("ix_try_on_jobs_status", table_name="try_on_jobs")
    op.drop_index("ix_try_on_jobs_user_key", table_name="try_on_jobs")
    op.drop_table("try_on_jobs")
