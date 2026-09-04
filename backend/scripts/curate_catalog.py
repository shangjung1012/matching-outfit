import argparse
import csv
import json
import math
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from app.services.fashion_clip import fashion_clip
from app.services.garment_classifier import classify_garment_zone


DEFAULT_POSITIVE_PROMPTS = [
    "modern stylish everyday clothing",
    "clean contemporary fashion garment",
    "versatile minimal wearable clothing",
    "elegant well designed fashion item",
]
DEFAULT_NEGATIVE_PROMPTS = [
    "outdated old fashioned clothing",
    "novelty costume garment",
    "overly ornate difficult to style clothing",
    "cheap looking graphic fashion item",
]
DEFAULT_EXCLUDED_TYPES = {
    "boxers",
    "bra",
    "briefs",
    "innerwear vests",
    "lounge pants",
    "night suits",
    "robe",
    "socks",
    "stockings",
}
DEFAULT_QUOTAS = {
    "upper_body": 180,
    "lower_body": 150,
    "one_piece": 80,
    "accessory": 120,
}


def parse_quotas(value: str) -> dict[str, int]:
    quotas: dict[str, int] = {}
    for part in value.split(","):
        zone, count = part.split("=", 1)
        quotas[zone.strip()] = int(count)
    unknown = set(quotas) - set(DEFAULT_QUOTAS)
    if unknown:
        raise ValueError(f"Unknown garment zones in quota: {sorted(unknown)}")
    return quotas


def normalized_key(value: str | None) -> str:
    return (value or "unknown").strip().lower() or "unknown"


def percentile_scale(values: np.ndarray) -> np.ndarray:
    if len(values) == 0:
        return values
    low, high = np.quantile(values, [0.05, 0.95])
    if high - low < 1e-8:
        return np.full_like(values, 0.5, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0).astype(np.float32)


def technical_quality(path: Path) -> float:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((256, 256))
            pixels = np.asarray(image, dtype=np.float32)
    except Exception:
        return 0.0
    gray = pixels.mean(axis=2)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    foreground_ratio = float((gray < 245).mean())
    edges = np.asarray(
        Image.fromarray(gray.astype(np.uint8)).filter(ImageFilter.FIND_EDGES),
        dtype=np.float32,
    )
    edge_strength = float(edges.std())
    exposure_score = max(0.0, 1.0 - abs(brightness - 190.0) / 190.0)
    contrast_score = min(1.0, contrast / 60.0)
    edge_score = min(1.0, edge_strength / 55.0)
    occupancy_score = max(0.0, 1.0 - abs(foreground_ratio - 0.35) / 0.45)
    return float(
        0.25 * exposure_score
        + 0.25 * contrast_score
        + 0.20 * edge_score
        + 0.30 * occupancy_score
    )


def metadata_quality(row: dict[str, str]) -> float:
    fields = [
        "gender",
        "masterCategory",
        "subCategory",
        "articleType",
        "baseColour",
        "season",
        "usage",
        "productDisplayName",
    ]
    return sum(bool((row.get(field) or "").strip()) for field in fields) / len(fields)


def eligible_rows(
    csv_path: Path,
    image_dir: Path,
    allowed_genders: set[str],
    excluded_types: set[str],
) -> tuple[list[dict[str, str]], list[str]]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        for row in reader:
            identifier = (row.get("id") or "").strip()
            if not identifier:
                continue
            gender = normalized_key(row.get("gender"))
            article_type = normalized_key(row.get("articleType"))
            zone = classify_garment_zone(row.get("articleType"), row.get("subCategory"))
            if gender not in allowed_genders or article_type in excluded_types or zone == "other":
                continue
            image_path = image_dir / f"{identifier}.jpg"
            if not image_path.exists():
                continue
            row["garment_zone"] = zone
            row["image_path"] = str(image_path)
            rows.append(row)
    return rows, fieldnames


def read_prompts(path: Path | None) -> list[str]:
    if path is None:
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def score_rows(
    rows: list[dict[str, str]],
    batch_size: int,
    trend_prompts: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    positive = np.asarray(fashion_clip.encode_texts(DEFAULT_POSITIVE_PROMPTS), dtype=np.float32)
    negative = np.asarray(fashion_clip.encode_texts(DEFAULT_NEGATIVE_PROMPTS), dtype=np.float32)
    trend = (
        np.asarray(fashion_clip.encode_texts(trend_prompts), dtype=np.float32)
        if trend_prompts
        else None
    )
    embeddings: list[np.ndarray] = []
    fashion_raw: list[float] = []
    trend_raw: list[float] = []
    quality: list[float] = []
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        paths = [row["image_path"] for row in batch]
        vectors = np.asarray(fashion_clip.encode_images(paths), dtype=np.float32)
        embeddings.append(vectors)
        fashion_raw.extend((vectors @ positive.T).mean(axis=1) - (vectors @ negative.T).mean(axis=1))
        if trend is None:
            trend_raw.extend([0.5] * len(batch))
        else:
            trend_raw.extend((vectors @ trend.T).mean(axis=1))
        quality.extend(technical_quality(Path(path)) for path in paths)
        print(f"Scored {min(start + len(batch), len(rows))}/{len(rows)} images")
    return (
        np.concatenate(embeddings, axis=0),
        percentile_scale(np.asarray(fashion_raw, dtype=np.float32)),
        percentile_scale(np.asarray(trend_raw, dtype=np.float32)) if trend is not None else np.asarray(trend_raw, dtype=np.float32),
        np.asarray(quality, dtype=np.float32),
    )


def select_balanced(
    rows: list[dict[str, str]],
    embeddings: np.ndarray,
    final_scores: np.ndarray,
    quotas: dict[str, int],
    duplicate_threshold: float,
    color_cap_ratio: float,
    article_cap_ratio: float,
) -> list[int]:
    selected: list[int] = []
    selected_by_zone: dict[str, list[int]] = {zone: [] for zone in quotas}
    color_counts: dict[str, Counter] = {zone: Counter() for zone in quotas}
    article_counts: dict[str, Counter] = {zone: Counter() for zone in quotas}

    def is_duplicate(index: int, zone: str) -> bool:
        existing = selected_by_zone[zone]
        if not existing:
            return False
        similarities = embeddings[existing] @ embeddings[index]
        return bool(float(similarities.max()) >= duplicate_threshold)

    def attempt(enforce_caps: bool) -> None:
        for zone, quota in quotas.items():
            color_cap = max(1, math.ceil(quota * color_cap_ratio))
            article_cap = max(1, math.ceil(quota * article_cap_ratio))
            candidates = sorted(
                (
                    index
                    for index, row in enumerate(rows)
                    if row["garment_zone"] == zone and index not in selected_by_zone[zone]
                ),
                key=lambda index: float(final_scores[index]),
                reverse=True,
            )
            for index in candidates:
                if len(selected_by_zone[zone]) >= quota:
                    break
                row = rows[index]
                color = normalized_key(row.get("baseColour"))
                article = normalized_key(row.get("articleType"))
                if enforce_caps and (
                    color_counts[zone][color] >= color_cap
                    or article_counts[zone][article] >= article_cap
                ):
                    continue
                if is_duplicate(index, zone):
                    continue
                selected.append(index)
                selected_by_zone[zone].append(index)
                color_counts[zone][color] += 1
                article_counts[zone][article] += 1

    attempt(enforce_caps=True)
    attempt(enforce_caps=False)
    return sorted(selected, key=lambda index: float(final_scores[index]), reverse=True)


def export_images(
    rows: list[dict[str, str]],
    indexes: list[int],
    source_dir: Path,
    destination: Path,
    max_edge: int,
) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for index in indexes:
        identifier = rows[index]["id"]
        source = source_dir / f"{identifier}.jpg"
        if not source.exists():
            continue
        target = destination / f"{identifier}.jpg"
        if max_edge <= 0:
            shutil.copy2(source, target)
        else:
            with Image.open(source) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
                image.thumbnail((max_edge, max_edge))
                image.save(target, format="JPEG", quality=85, optimize=True)
        copied += 1
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Automatically curate a balanced fashion catalog.")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--export-image-dir", type=Path)
    parser.add_argument("--copy-images", action="store_true")
    parser.add_argument("--max-image-edge", type=int, default=768)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--genders", default="Men,Women,Unisex")
    parser.add_argument("--trend-prompts", type=Path)
    parser.add_argument(
        "--quotas",
        default=",".join(f"{zone}={count}" for zone, count in DEFAULT_QUOTAS.items()),
    )
    parser.add_argument("--duplicate-threshold", type=float, default=0.985)
    parser.add_argument("--color-cap-ratio", type=float, default=0.20)
    parser.add_argument("--article-cap-ratio", type=float, default=0.25)
    args = parser.parse_args()

    quotas = parse_quotas(args.quotas)
    genders = {normalized_key(value) for value in args.genders.split(",")}
    rows, original_fields = eligible_rows(
        args.csv,
        args.image_dir,
        genders,
        DEFAULT_EXCLUDED_TYPES,
    )
    if not rows:
        raise SystemExit("No eligible rows with matching images were found")
    print(f"Metadata filter retained {len(rows)} images")
    trend_prompts = read_prompts(args.trend_prompts)
    embeddings, fashion_scores, trend_scores, quality_scores = score_rows(
        rows, args.batch_size, trend_prompts
    )
    metadata_scores = np.asarray([metadata_quality(row) for row in rows], dtype=np.float32)
    final_scores = (
        0.55 * fashion_scores
        + 0.20 * quality_scores
        + 0.15 * metadata_scores
        + 0.10 * trend_scores
    )
    indexes = select_balanced(
        rows,
        embeddings,
        final_scores,
        quotas,
        args.duplicate_threshold,
        args.color_cap_ratio,
        args.article_cap_ratio,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    score_fields = [
        "garment_zone",
        "fashion_score",
        "quality_score",
        "metadata_score",
        "trend_score",
        "curation_score",
    ]
    output_fields = list(dict.fromkeys([*original_fields, *score_fields]))
    with (args.output_dir / "selected_styles.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        for index in indexes:
            row = dict(rows[index])
            row.update(
                fashion_score=round(float(fashion_scores[index]), 6),
                quality_score=round(float(quality_scores[index]), 6),
                metadata_score=round(float(metadata_scores[index]), 6),
                trend_score=round(float(trend_scores[index]), 6),
                curation_score=round(float(final_scores[index]), 6),
            )
            writer.writerow(row)
    selected_ids = [int(rows[index]["id"]) for index in indexes]
    (args.output_dir / "selected_ids.json").write_text(
        json.dumps(selected_ids, indent=2), encoding="utf-8"
    )
    zone_counts = Counter(rows[index]["garment_zone"] for index in indexes)
    copied = 0
    if args.copy_images:
        copied = export_images(
            rows,
            indexes,
            args.export_image_dir or args.image_dir,
            args.output_dir / "images",
            args.max_image_edge,
        )
    summary = {
        "eligible_count": len(rows),
        "selected_count": len(indexes),
        "copied_image_count": copied,
        "zone_counts": dict(zone_counts),
        "quotas": quotas,
        "fashion_clip_model": "patrickjohncyh/fashion-clip",
        "weights": {"fashion": 0.55, "quality": 0.20, "metadata": 0.15, "trend": 0.10},
    }
    (args.output_dir / "curation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
