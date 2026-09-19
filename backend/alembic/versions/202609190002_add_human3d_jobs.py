"""add human3d reconstruction jobs

Revision ID: 202609190002
Revises: 202609190001
Create Date: 2026-09-19 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "202609190002"
down_revision = "202609190001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "human3d_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_key", sa.String(length=120), nullable=False),
        sa.Column("try_on_job_id", sa.Uuid(), nullable=False),
        sa.Column("remote_job_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("artifact_format", sa.String(length=24), nullable=True),
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
            name="ck_human3d_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["try_on_job_id"], ["try_on_jobs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_human3d_jobs_user_key", "human3d_jobs", ["user_key"])
    op.create_index("ix_human3d_jobs_try_on_job_id", "human3d_jobs", ["try_on_job_id"])
    op.create_index("ix_human3d_jobs_remote_job_id", "human3d_jobs", ["remote_job_id"], unique=True)
    op.create_index("ix_human3d_jobs_status", "human3d_jobs", ["status"])
    op.create_index("ix_human3d_jobs_expires_at", "human3d_jobs", ["expires_at"])


def downgrade() -> None:
    op.drop_table("human3d_jobs")
