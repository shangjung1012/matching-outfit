"""replace object keys with remote try-on job IDs

Revision ID: 202609070001
Revises: 202609060002
Create Date: 2026-09-07 09:27:53
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609070001"
down_revision: Union[str, None] = "202609060002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("try_on_jobs", sa.Column("remote_job_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_try_on_jobs_remote_job_id",
        "try_on_jobs",
        ["remote_job_id"],
        unique=True,
    )
    op.execute(
        "UPDATE try_on_jobs SET status = 'failed', "
        "error_message = 'Storage architecture changed; submit this try-on again' "
        "WHERE remote_job_id IS NULL"
    )
    op.drop_column("try_on_jobs", "result_object_key")
    op.drop_column("try_on_jobs", "cloth_object_key")
    op.drop_column("try_on_jobs", "person_object_key")


def downgrade() -> None:
    op.add_column(
        "try_on_jobs",
        sa.Column("person_object_key", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "try_on_jobs",
        sa.Column("cloth_object_key", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "try_on_jobs",
        sa.Column("result_object_key", sa.String(length=500), nullable=True),
    )
    op.drop_index("ix_try_on_jobs_remote_job_id", table_name="try_on_jobs")
    op.drop_column("try_on_jobs", "remote_job_id")
