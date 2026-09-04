"""Compare and, by default, apply the shared fashion-knowledge snapshot."""

import argparse
from pathlib import Path

from app.core.config import settings
from app.db.session import SessionLocal
from app.knowledge.snapshot import apply_snapshot, compare_snapshot, load_snapshot


def default_snapshot_path() -> Path:
    return Path(settings.article_data_dir).parent / "fashion_knowledge.snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare the local database with the shared snapshot and apply newer data."
    )
    parser.add_argument("--snapshot", type=Path, default=default_snapshot_path())
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Report differences without changing the database.",
    )
    return parser.parse_args()


def _print_urls(label: str, urls: list[str]) -> None:
    print(f"{label}: {len(urls)}")
    for url in urls:
        print(f"  - {url}")


def main() -> None:
    args = parse_args()
    if not args.snapshot.exists():
        raise SystemExit(f"Snapshot does not exist: {args.snapshot}")
    snapshot = load_snapshot(args.snapshot)
    if snapshot.embedding_dimensions != settings.knowledge_embedding_dimensions:
        raise SystemExit(
            "Snapshot embedding dimensions do not match this application: "
            f"{snapshot.embedding_dimensions} != {settings.knowledge_embedding_dimensions}"
        )

    with SessionLocal() as db:
        comparison = compare_snapshot(
            db, snapshot, settings.knowledge_embedding_dimensions
        )
        _print_urls("Missing locally", comparison.missing_urls)
        _print_urls("Outdated locally", comparison.outdated_urls)
        _print_urls("Local-only (preserved)", comparison.local_only_urls)
        if not comparison.is_behind:
            print(f"Database is up to date with revision {snapshot.content_digest[:12]}.")
            return
        if args.check_only:
            print("Changes found; --check-only left the database unchanged.")
            return
        articles, observations = apply_snapshot(db, snapshot, comparison)
        print(
            f"Applied revision {snapshot.content_digest[:12]}: "
            f"{articles} articles and {observations} observations updated."
        )


if __name__ == "__main__":
    main()
