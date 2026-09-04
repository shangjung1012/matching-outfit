"""rebuild try-on jobs for multiple reference images

Revision ID: 202609110001
Revises: 202609050004
Create Date: 2026-09-11 00:01:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609110001"
down_revision: Union[str, None] = "202609050004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_try_on_jobs(reference_column: sa.Column) -> None:
    op.create_table(
        "try_on_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_key", sa.String(length=120), nullable=False),
        reference_column,
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("remote_job_id", sa.Uuid(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_try_on_jobs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_try_on_jobs_user_key", "try_on_jobs", ["user_key"])
    op.create_index("ix_try_on_jobs_status", "try_on_jobs", ["status"])
    op.create_index("ix_try_on_jobs_expires_at", "try_on_jobs", ["expires_at"])
    op.create_index(
        "ix_try_on_jobs_remote_job_id",
        "try_on_jobs",
        ["remote_job_id"],
        unique=True,
    )


def upgrade() -> None:
    op.drop_table("try_on_jobs")
    _create_try_on_jobs(sa.Column("reference_types", sa.JSON(), nullable=False))


def downgrade() -> None:
    op.drop_table("try_on_jobs")
    _create_try_on_jobs(sa.Column("cloth_type", sa.String(length=16), nullable=False))
    op.create_check_constraint(
        "ck_try_on_jobs_cloth_type",
        "try_on_jobs",
        "cloth_type IN ('upper', 'lower', 'overall')",
    )
