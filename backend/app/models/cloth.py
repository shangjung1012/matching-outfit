from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.sqltypes import DateTime

from app.models.base import Base


class Cloth(Base):
    __tablename__ = "clothes"
    __table_args__ = (
        CheckConstraint(
            "garment_zone IN ('upper_body', 'lower_body', 'one_piece', 'accessory', 'other')",
            name="ck_clothes_garment_zone",
        ),
        CheckConstraint("price >= 0", name="ck_clothes_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_item_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(40), nullable=True)
    master_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sub_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    article_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_colour: Mapped[str | None] = mapped_column(String(80), nullable=True)
    season: Mapped[str | None] = mapped_column(String(40), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_display_name: Mapped[str] = mapped_column(String(255))
    garment_zone: Mapped[str] = mapped_column(String(24), index=True)
    price: Mapped[int] = mapped_column(Integer)
    image_path: Mapped[str] = mapped_column(String(500))
    image_url: Mapped[str] = mapped_column(String(500))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
