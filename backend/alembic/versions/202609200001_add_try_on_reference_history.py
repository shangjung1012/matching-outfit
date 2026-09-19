"""add persistent try-on reference history

Revision ID: 202609200001
Revises: 202609190004
Create Date: 2026-09-20 00:01:00
"""

from alembic import op
import sqlalchemy as sa


revision = "202609200001"
down_revision = "202609190004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_user_wardrobe_items_category",
        "user_wardrobe_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_user_wardrobe_items_category",
        "user_wardrobe_items",
        "category IN ('upper_body', 'lower_body', 'one_piece', 'shoes', 'bags')",
    )
    op.add_column(
        "try_on_jobs",
        sa.Column("history_hidden_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_try_on_jobs_history_hidden_at",
        "try_on_jobs",
        ["history_hidden_at"],
    )
    op.create_table(
        "try_on_job_references",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("try_on_job_id", sa.Uuid(), nullable=False),
        sa.Column("reference_type", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("cloth_id", sa.Integer(), nullable=True),
        sa.Column("wardrobe_item_id", sa.Integer(), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "reference_type IN ('upper', 'lower', 'overall', 'shoe', 'bag')",
            name="ck_try_on_job_references_type",
        ),
        sa.CheckConstraint(
            "source IN ('catalog', 'wardrobe', 'upload')",
            name="ck_try_on_job_references_source",
        ),
        sa.ForeignKeyConstraint(
            ["try_on_job_id"], ["try_on_jobs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["cloth_id"], ["clothes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["wardrobe_item_id"], ["user_wardrobe_items.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "try_on_job_id",
            "reference_type",
            name="uq_try_on_job_references_job_type",
        ),
    )
    op.create_index(
        "ix_try_on_job_references_try_on_job_id",
        "try_on_job_references",
        ["try_on_job_id"],
    )
    op.create_index(
        "ix_try_on_job_references_cloth_id",
        "try_on_job_references",
        ["cloth_id"],
    )
    op.create_index(
        "ix_try_on_job_references_wardrobe_item_id",
        "try_on_job_references",
        ["wardrobe_item_id"],
    )


def downgrade() -> None:
    op.drop_table("try_on_job_references")
    op.drop_index("ix_try_on_jobs_history_hidden_at", table_name="try_on_jobs")
    op.drop_column("try_on_jobs", "history_hidden_at")
    op.drop_constraint(
        "ck_user_wardrobe_items_category",
        "user_wardrobe_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_user_wardrobe_items_category",
        "user_wardrobe_items",
        "category IN ('upper_body', 'lower_body', 'shoes')",
    )
