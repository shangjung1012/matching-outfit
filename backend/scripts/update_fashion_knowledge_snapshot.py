"""Discover new articles, import processed knowledge, and export a shared snapshot."""

import argparse
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.knowledge.ingestion.article_collector import ArticleCollector
from app.knowledge.ingestion.article_discovery import (
    SOURCE_BY_KEY,
    SOURCES,
    ArticleDiscovery,
    discover_new_articles,
)
from app.knowledge.ingestion.article_extractor import ArticleKnowledgeExtractor
from app.knowledge.ingestion.db_importer import import_knowledge_records
from app.knowledge.snapshot import build_snapshot, write_snapshot
from app.knowledge.store import FashionKnowledgeStore
from app.models.fashion_knowledge import FashionArticle
from app.services.integration_tools.llm import LLM
from app.services.integration_tools.text_embeddings import TextEmbeddingService


def default_snapshot_path() -> Path:
    return Path(settings.article_data_dir).parent / "fashion_knowledge.snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover and import new fashion articles, then export processed database "
            "knowledge without raw article bodies or images."
        )
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=sorted(SOURCE_BY_KEY),
        dest="source_keys",
        help="Source key to scan; repeat to select multiple sources (default: all).",
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=0,
        help="Pages to scan per source. 0 means auto-scan until no unseen links.",
    )
    parser.add_argument("--per-source-limit", type=int, default=2, choices=range(1, 21))
    parser.add_argument("--max-articles", type=int, default=8, choices=range(1, 13))
    parser.add_argument("--snapshot", type=Path, default=default_snapshot_path())
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Skip discovery and API calls; export the current database only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = FashionKnowledgeStore(settings.article_data_dir)
    failures = 0
    with SessionLocal() as db:
        if not args.export_only:
            sources = (
                [SOURCE_BY_KEY[key] for key in args.source_keys]
                if args.source_keys
                else list(SOURCES)
            )
            collector = ArticleCollector(
                settings.allowed_article_domains,
                settings.article_user_agent,
            )
            discovery_batch = discover_new_articles(
                ArticleDiscovery(collector),
                sources,
                set(db.scalars(select(FashionArticle.source_url))),
                page_limit=args.page_limit,
                per_source_limit=args.per_source_limit,
                max_articles=args.max_articles,
            )
            for source_key, message in discovery_batch.errors.items():
                print(f"Discovery failed for {source_key}: {message}")
            if discovery_batch.articles:
                extractor = ArticleKnowledgeExtractor(LLM())
                embedder = TextEmbeddingService(
                    settings.openai_api_key,
                    settings.knowledge_embedding_model,
                    settings.knowledge_embedding_dimensions,
                )
                for candidate in discovery_batch.articles:
                    try:
                        print(f"Collecting: {candidate.url}")
                        article = collector.collect(candidate.url)
                        store.save_collected(article)
                        record = extractor.extract(article)
                        store.save_record(record)
                        _, observations, embedded = import_knowledge_records(
                            db, [record], embedder
                        )
                        print(
                            f"  imported {observations} observations and "
                            f"{embedded} embeddings"
                        )
                    except Exception as error:
                        db.rollback()
                        failures += 1
                        print(f"  failed: {error}")
            else:
                print("No unrecorded articles were discovered.")

        snapshot = build_snapshot(db, settings.knowledge_embedding_dimensions)
        changed = write_snapshot(args.snapshot, snapshot)
        action = "Wrote" if changed else "Unchanged"
        observation_count = sum(
            len(article.observations) for article in snapshot.articles
        )
        print(
            f"{action} snapshot {args.snapshot}: {len(snapshot.articles)} articles, "
            f"{observation_count} observations, revision {snapshot.content_digest[:12]}"
        )
    if failures:
        print(f"Completed with {failures} article failures; successful changes were exported.")


if __name__ == "__main__":
    main()
