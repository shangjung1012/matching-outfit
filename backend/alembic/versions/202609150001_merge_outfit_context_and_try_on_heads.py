"""merge outfit context and try-on migration branches

Revision ID: 202609150001
Revises: 202609060001, 202609110001
Create Date: 2026-09-15 00:01:00
"""

from typing import Sequence, Union


revision: str = "202609150001"
down_revision: tuple[str, str] = ("202609060001", "202609110001")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge point only; parent migrations contain the schema changes."""


def downgrade() -> None:
    """Split the migration history back into its two parent branches."""
