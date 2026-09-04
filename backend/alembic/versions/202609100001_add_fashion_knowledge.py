"""add structured fashion knowledge tables

Revision ID: 202609100001
Revises: 202609090001
Create Date: 2026-09-10 11:38:44
"""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


revision: str = "202609100001"
down_revision: Union[str, None] = "202609090001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fashion_articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("source_name", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("language", sa.String(length=40), nullable=True),
        sa.Column("article_summary", sa.Text(), nullable=False),
        sa.Column("extraction_notes", sa.JSON(), nullable=False),
        sa.Column("extraction_model", sa.String(length=160), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fashion_articles_source_name", "fashion_articles", ["source_name"])
    op.create_index(
        "ix_fashion_articles_source_url", "fashion_articles", ["source_url"], unique=True
    )

    op.create_table(
        "fashion_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.String(length=64), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("audiences", sa.JSON(), nullable=False),
        sa.Column("occasions", sa.JSON(), nullable=False),
        sa.Column("climates", sa.JSON(), nullable=False),
        sa.Column("seasons", sa.JSON(), nullable=False),
        sa.Column("styles", sa.JSON(), nullable=False),
        sa.Column("garments", sa.JSON(), nullable=False),
        sa.Column("colors", sa.JSON(), nullable=False),
        sa.Column("materials", sa.JSON(), nullable=False),
        sa.Column("silhouettes", sa.JSON(), nullable=False),
        sa.Column("styling_actions", sa.JSON(), nullable=False),
        sa.Column("avoid_when", sa.JSON(), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("embedding", Vector(dim=512), nullable=True),
        sa.Column("embedding_model", sa.String(length=160), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_fashion_observations_confidence",
        ),
        sa.CheckConstraint(
            "signal_type IN ('timeless', 'current_trend', 'editorial_example')",
            name="ck_fashion_observations_signal_type",
        ),
        sa.ForeignKeyConstraint(["article_id"], ["fashion_articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fashion_observations_article_id", "fashion_observations", ["article_id"]
    )
    op.create_index(
        "ix_fashion_observations_is_active", "fashion_observations", ["is_active"]
    )
    op.create_index(
        "ix_fashion_observations_observation_id",
        "fashion_observations",
        ["observation_id"],
        unique=True,
    )
    op.create_index(
        "ix_fashion_observations_signal_type", "fashion_observations", ["signal_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_fashion_observations_signal_type", table_name="fashion_observations")
    op.drop_index("ix_fashion_observations_observation_id", table_name="fashion_observations")
    op.drop_index("ix_fashion_observations_is_active", table_name="fashion_observations")
    op.drop_index("ix_fashion_observations_article_id", table_name="fashion_observations")
    op.drop_table("fashion_observations")
    op.drop_index("ix_fashion_articles_source_url", table_name="fashion_articles")
    op.drop_index("ix_fashion_articles_source_name", table_name="fashion_articles")
    op.drop_table("fashion_articles")
