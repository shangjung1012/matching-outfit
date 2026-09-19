"""Add user profile login state and repair the legacy revision collision.

Revision ID: 202609190004
Revises: 202609190003
Create Date: 2026-09-19 13:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "202609190004"
down_revision = "202609190003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``202609190003`` was originally released as the user-profile migration.
    # It was later reused for the wardrobe migration, leaving already-upgraded
    # databases reporting revision 202609190003 with ``user_profile`` present
    # and ``user_wardrobe_items`` absent.  Make this successor migration
    # idempotent so both that legacy state and a fresh installation converge.
    existing_tables = sa.inspect(op.get_bind()).get_table_names()

    if "user_profile" not in existing_tables:
        op.create_table(
            "user_profile",
            sa.Column("user_key", sa.String(length=120), nullable=False),
            sa.Column("do_test", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.PrimaryKeyConstraint("user_key"),
        )

    if "user_wardrobe_items" not in existing_tables:
        op.create_table(
            "user_wardrobe_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_key", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("category", sa.String(length=24), nullable=False),
            sa.Column("stored_filename", sa.String(length=100), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("is_favorite", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.CheckConstraint(
                "category IN ('upper_body', 'lower_body', 'shoes')",
                name="ck_user_wardrobe_items_category",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("stored_filename"),
        )
        op.create_index("ix_user_wardrobe_items_user_key", "user_wardrobe_items", ["user_key"])
        op.create_index(
            "ix_user_wardrobe_items_user_created",
            "user_wardrobe_items",
            ["user_key", "created_at"],
        )
        op.create_index(
            "ix_user_wardrobe_items_user_favorite",
            "user_wardrobe_items",
            ["user_key", "is_favorite"],
        )


def downgrade() -> None:
    op.drop_table("user_profile")
