"""merge try-on and fashion knowledge migration branches

Revision ID: 202609120001
Revises: 202609070001, 202609100001
Create Date: 2026-09-12 16:52:07
"""

from typing import Sequence, Union


revision: str = "202609120001"
down_revision: tuple[str, str] = ("202609070001", "202609100001")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge point only; parent migrations contain the schema changes."""


def downgrade() -> None:
    """Split the migration history back into its two parent branches."""
