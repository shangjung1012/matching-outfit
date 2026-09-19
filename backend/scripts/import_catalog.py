import argparse
import csv
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.cloth import Cloth
from app.services.garment_classifier import classify_garment_zone

OUTFIT_DEMO_ZONES = {"upper_body", "lower_body", "one_piece"}
OUTFIT_DEMO_EXCLUDED_TERMS = {
    "baby dolls",
    "boxers",
    "bra",
    "briefs",
    "bodysuit",
    "camisoles",
    "innerwear",
    "lingerie",
    "lounge pants",
    "lounge shorts",
    "night suit",
    "nightdress",
    "pyjama",
    "robe",
    "shapewear",
    "socks",
    "stockings",
    "swimwear",
    "bikini",
    "tights",
    "underwear",
}

HM_GROUP_TO_SUBCATEGORY = {
    "garment upper body": "Topwear",
    "garment lower body": "Bottomwear",
    "garment full body": "Dress",
    "swimwear": "Swimwear",
}
HM_ARTICLE_TYPE_MAP = {
    "blazer": "Blazers",
    "dress": "Dresses",
    "jacket": "Jackets",
    "jumpsuit/playsuit": "Jumpsuit",
    "leggings/tights": "Leggings",
    "shirt": "Shirts",
    "skirt": "Skirts",
    "sweater": "Sweaters",
    "t-shirt": "Tshirts",
    "top": "Tops",
    # Keep sleeveless tops separate so users can exclude tank/vest tops without
    # excluding every generic top in the catalog.
    "vest top": "Vest top",
}


def optional_int(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    return int(float(value))


def positive_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def hm_gender(row: dict[str, str]) -> str | None:
    context = " ".join(
        str(row.get(field) or "")
        for field in ("index_group_name", "index_name", "section_name")
    ).lower()
    if any(term in context for term in ("ladies", "women", "divided")):
        return "Women"
    if any(term in context for term in ("men", "menswear")):
        return "Men"
    return "Unisex" if context else None


def normalize_hm_row(row: dict[str, str]) -> dict[str, str | None]:
    product_group = str(row.get("product_group_name") or "").strip()
    product_type = str(row.get("product_type_name") or "").strip()
    return {
        "id": row.get("article_id"),
        "gender": hm_gender(row),
        "masterCategory": "Apparel",
        "subCategory": HM_GROUP_TO_SUBCATEGORY.get(product_group.lower(), product_group),
        "articleType": HM_ARTICLE_TYPE_MAP.get(product_type.lower(), product_type),
        "baseColour": row.get("colour_group_name")
        or row.get("perceived_colour_master_name"),
        "season": None,
        "year": None,
        "usage": None,
        "productDisplayName": row.get("prod_name") or row.get("detail_desc"),
        "price": row.get("price_twd"),
        "brandName": "H&M",
        "ageGroup": "Adults",
    }


def normalize_catalog_row(row: dict[str, str], dataset: str) -> dict[str, str | None]:
    return normalize_hm_row(row) if dataset == "hm" else row


def parse_zone_limits(value: str | None) -> dict[str, int]:
    if not value:
        return {}
    limits: dict[str, int] = {}
    for item in value.split(","):
        zone, separator, raw_limit = item.partition("=")
        if not separator or zone.strip() not in OUTFIT_DEMO_ZONES:
            raise argparse.ArgumentTypeError(f"Invalid zone limit: {item}")
        limit = positive_int(raw_limit.strip())
        if limit is None:
            raise argparse.ArgumentTypeError(f"Invalid zone limit: {item}")
        limits[zone.strip()] = limit
    return limits


def load_style_data(styles_json_dir: Path | None, source_id: int) -> dict[str, Any] | None:
    if styles_json_dir is None:
        return None
    path = styles_json_dir / f"{source_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def nested_type_name(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if not isinstance(value, dict):
        return None
    name = value.get("typeName")
    return str(name) if name else None


def price_fields(
    style_data: dict[str, Any] | None,
    default_price: int,
    csv_price: int | None = None,
) -> dict[str, int | None]:
    if style_data is None:
        return {
            "price": csv_price if csv_price is not None else default_price,
            "original_price": None,
            "discounted_price": None,
        }
    original_price = positive_int(style_data.get("price"))
    discounted_price = positive_int(style_data.get("discountedPrice"))
    effective_price = discounted_price if discounted_price is not None else original_price
    if effective_price is None:
        effective_price = csv_price
    return {
        "price": effective_price if effective_price is not None else default_price,
        "original_price": original_price,
        "discounted_price": discounted_price,
    }


def resolved_categories(
    row: dict[str, str], style_data: dict[str, Any] | None
) -> tuple[str | None, str | None, str | None]:
    data = style_data or {}
    return (
        nested_type_name(data, "masterCategory") or row.get("masterCategory"),
        nested_type_name(data, "subCategory") or row.get("subCategory"),
        nested_type_name(data, "articleType") or row.get("articleType"),
    )


def matches_outfit_demo_profile(
    row: dict[str, str], style_data: dict[str, Any] | None
) -> bool:
    _, sub_category, article_type = resolved_categories(row, style_data)
    zone = classify_garment_zone(article_type, sub_category)
    if zone not in OUTFIT_DEMO_ZONES:
        return False

    if str(row.get("gender") or "").strip().lower() in {"boys", "girls"}:
        return False

    age_group = str(
        (style_data or {}).get("ageGroup") or row.get("ageGroup") or ""
    ).strip().lower()
    if age_group and not age_group.startswith("adults"):
        return False

    item_text = f"{article_type or ''} {sub_category or ''}".strip().lower()
    return not any(term in item_text for term in OUTFIT_DEMO_EXCLUDED_TERMS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Kaggle Fashion Product Images metadata.")
    parser.add_argument("--dataset", choices=("myntra", "hm"), default="myntra")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--image-dir", default=Path("/data/images"), type=Path)
    parser.add_argument("--styles-json-dir", type=Path)
    parser.add_argument("--default-price", default=1000, type=int)
    parser.add_argument("--currency")
    parser.add_argument("--profile", choices=("all", "outfit-demo"), default="all")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--zone-limits", type=parse_zone_limits, default={})
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-workers", type=int, default=8)
    parser.add_argument("--prune-existing", action="store_true")
    args = parser.parse_args()

    skipped = filtered = json_loaded = 0
    print(f"Indexing JPG files in {args.image_dir}...", flush=True)
    available_images = {
        (path.stem.lstrip("0") or "0") if args.dataset == "hm" else path.stem: path
        for path in args.image_dir.glob("*.jpg")
    }
    print(f"Indexed {len(available_images)} JPG files.", flush=True)
    candidates: list[tuple[int, Path, dict[str, str]]] = []
    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            row = normalize_catalog_row(row, args.dataset)
            source_id = int(str(row["id"]))
            image_path = available_images.get(str(source_id))
            if image_path is None:
                skipped += 1
                continue
            if args.profile == "outfit-demo" and not matches_outfit_demo_profile(row, None):
                filtered += 1
                continue
            candidates.append((source_id, image_path, row))
    print(f"CSV prefilter kept {len(candidates)} candidates.", flush=True)

    rows_to_import: list[tuple[int, Path, dict[str, str], dict[str, Any] | None]] = []
    selected_zone_counts: Counter[str] = Counter()
    worker_count = max(1, args.json_workers)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for start in range(0, len(candidates), 500):
            batch = []
            for candidate in candidates[start : start + 500]:
                _, _, row = candidate
                _, sub_category, article_type = resolved_categories(row, None)
                zone = classify_garment_zone(article_type, sub_category)
                if args.zone_limits and selected_zone_counts[zone] >= args.zone_limits.get(
                    zone, 0
                ):
                    filtered += 1
                    continue
                batch.append(candidate)
            if not batch:
                continue
            if args.styles_json_dir is None:
                style_records: list[dict[str, Any] | None] = [None] * len(batch)
            else:
                style_records = list(
                    executor.map(
                        lambda item: load_style_data(args.styles_json_dir, item[0]),
                        batch,
                    )
                )
            for (source_id, image_path, row), style_data in zip(
                batch, style_records, strict=True
            ):
                if args.profile == "outfit-demo" and not matches_outfit_demo_profile(
                    row, style_data
                ):
                    filtered += 1
                    continue
                _, sub_category, article_type = resolved_categories(row, style_data)
                zone = classify_garment_zone(article_type, sub_category)
                if args.zone_limits and selected_zone_counts[zone] >= args.zone_limits.get(
                    zone, 0
                ):
                    filtered += 1
                    continue
                if style_data is not None:
                    json_loaded += 1
                rows_to_import.append((source_id, image_path, row, style_data))
                selected_zone_counts[zone] += 1
                if args.limit and len(rows_to_import) >= args.limit:
                    break
            quotas_met = args.zone_limits and all(
                selected_zone_counts[zone] >= limit
                for zone, limit in args.zone_limits.items()
            )
            if (args.limit and len(rows_to_import) >= args.limit) or quotas_met:
                break
            if len(rows_to_import) and len(rows_to_import) % 2000 < len(batch):
                print(
                    f"Loaded JSON metadata for {len(rows_to_import)} selected records...",
                    flush=True,
                )

    zone_counts = Counter()
    article_counts = Counter()
    for _, _, row, style_data in rows_to_import:
        _, sub_category, article_type = resolved_categories(row, style_data)
        zone_counts[classify_garment_zone(article_type, sub_category)] += 1
        article_counts[article_type or "Unknown"] += 1
    print(f"Selected {len(rows_to_import)} records by zone: {dict(zone_counts)}")
    print(f"Most common article types: {article_counts.most_common(12)}")
    if args.dry_run:
        print(
            f"Dry run only; loaded {json_loaded} JSON records; filtered {filtered} records; "
            f"skipped {skipped} missing images."
        )
        return

    if args.prune_existing and not rows_to_import:
        raise RuntimeError("Refusing to prune because the selected catalog is empty")

    imported = pruned = 0
    with SessionLocal() as db:
        existing: dict[int, Cloth] = {}
        source_ids = [source_id for source_id, _, _, _ in rows_to_import]
        for start in range(0, len(source_ids), 1000):
            batch_ids = source_ids[start : start + 1000]
            for cloth in db.scalars(select(Cloth).where(Cloth.source_item_id.in_(batch_ids))):
                if cloth.source_item_id is not None:
                    existing[cloth.source_item_id] = cloth

        if args.prune_existing:
            result = db.execute(
                delete(Cloth).where(
                    Cloth.source_item_id.is_not(None),
                    Cloth.source_item_id.not_in(source_ids),
                )
            )
            pruned = result.rowcount or 0

        for source_id, image_path, row, style_data in rows_to_import:
            cloth = existing.get(source_id)
            master_category, sub_category, article_type = resolved_categories(row, style_data)
            values = {
                "gender": (style_data or {}).get("gender") or row.get("gender"),
                "master_category": master_category,
                "sub_category": sub_category,
                "article_type": article_type,
                "base_colour": (style_data or {}).get("baseColour") or row.get("baseColour"),
                "season": (style_data or {}).get("season") or row.get("season"),
                "year": positive_int((style_data or {}).get("year")) or optional_int(row.get("year")),
                "usage": (style_data or {}).get("usage") or row.get("usage"),
                "product_display_name": (style_data or {}).get("productDisplayName")
                or row.get("productDisplayName")
                or f"Item {source_id}",
                "garment_zone": classify_garment_zone(article_type, sub_category),
                **price_fields(
                    style_data,
                    args.default_price,
                    positive_int(row.get("prices") or row.get("price")),
                ),
                "currency": (
                    args.currency
                    or ("TWD" if args.dataset == "hm" else settings.catalog_currency)
                ).upper(),
                "brand_name": (style_data or {}).get("brandName") or row.get("brandName"),
                "age_group": (style_data or {}).get("ageGroup") or row.get("ageGroup"),
                "image_path": str(image_path),
                "image_url": f"/media/{image_path.name}",
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
    print(
        f"Imported or updated {imported} clothes; loaded {json_loaded} JSON records; "
        f"pruned {pruned} old records; filtered {filtered} records; "
        f"skipped {skipped} missing images."
    )


if __name__ == "__main__":
    main()
