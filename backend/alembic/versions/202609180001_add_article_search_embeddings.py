"""Cache article title/summary vectors for semantic article browsing."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "202609180001"
down_revision = "202609150003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fashion_articles", sa.Column("search_embedding", Vector(512), nullable=True))
    op.add_column("fashion_articles", sa.Column("search_embedding_model", sa.String(160), nullable=True))
    op.add_column("fashion_articles", sa.Column("search_embedding_text", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("fashion_articles", "search_embedding_text")
    op.drop_column("fashion_articles", "search_embedding_model")
    op.drop_column("fashion_articles", "search_embedding")
