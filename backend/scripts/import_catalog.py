import argparse
import csv
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.cloth import Cloth
from app.services.garment_classifier import classify_garment_zone


def optional_int(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    return int(float(value))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Kaggle Fashion Product Images metadata.")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--image-dir", default=Path("/data/images"), type=Path)
    parser.add_argument("--default-price", default=1000, type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    imported = skipped = 0
    with args.csv.open(encoding="utf-8-sig", newline="") as handle, SessionLocal() as db:
        for row_number, row in enumerate(csv.DictReader(handle), start=1):
            if args.limit and row_number > args.limit:
                break
            source_id = int(row["id"])
            image_path = args.image_dir / f"{source_id}.jpg"
            if not image_path.exists():
                skipped += 1
                continue
            cloth = db.scalar(select(Cloth).where(Cloth.source_item_id == source_id))
            values = {
                "gender": row.get("gender"),
                "master_category": row.get("masterCategory"),
                "sub_category": row.get("subCategory"),
                "article_type": row.get("articleType"),
                "base_colour": row.get("baseColour"),
                "season": row.get("season"),
                "year": optional_int(row.get("year")),
                "usage": row.get("usage"),
                "product_display_name": row.get("productDisplayName") or f"Item {source_id}",
                "garment_zone": classify_garment_zone(row.get("articleType"), row.get("subCategory")),
                "price": args.default_price,
                "image_path": str(image_path),
                "image_url": f"/media/{source_id}.jpg",
            }
            if cloth:
                for key, value in values.items():
                    setattr(cloth, key, value)
            else:
                db.add(Cloth(source_item_id=source_id, **values))
            imported += 1
            if imported % 500 == 0:
                db.commit()
        db.commit()
    print(f"Imported or updated {imported} clothes; skipped {skipped} missing images.")


if __name__ == "__main__":
    main()
