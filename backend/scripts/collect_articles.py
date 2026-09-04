import argparse
from pathlib import Path

from app.core.config import settings
from app.knowledge.ingestion.article_collector import ArticleCollector
from app.knowledge.ingestion.article_extractor import ArticleKnowledgeExtractor
from app.knowledge.store import FashionKnowledgeStore
from app.services.integration_tools.llm import LLM


def load_urls(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect allowlisted fashion articles and extract outfit observations."
    )
    parser.add_argument("--url-file", type=Path, required=True)
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--download-images", action="store_true")
    parser.add_argument("--max-images", type=int, default=4)
    parser.add_argument("--skip-robots-check", action="store_true")
    args = parser.parse_args()

    store = FashionKnowledgeStore(settings.article_data_dir)
    collector = ArticleCollector(
        settings.allowed_article_domains,
        settings.article_user_agent,
    )
    extractor = None
    if not args.collect_only:
        extractor = ArticleKnowledgeExtractor(LLM())

    urls = load_urls(args.url_file)
    if not urls:
        raise SystemExit("The URL file contains no article URLs")
    failures = 0
    for url in urls:
        try:
            print(f"Collecting: {url}")
            article = collector.collect(url, check_robots=not args.skip_robots_check)
            if args.download_images:
                image_dir = store.images_dir / article.source_name.replace(".", "_")
                article = collector.download_images(
                    article, image_dir, max_images=max(0, args.max_images)
                )
            raw_path = store.save_collected(article)
            print(f"  saved raw article: {raw_path}")
            if extractor is not None:
                record = extractor.extract(article)
                record_path = store.save_record(record)
                print(
                    f"  extracted {len(record.extraction.observations)} observations: {record_path}"
                )
        except Exception as error:  # keep a small batch moving while reporting each failure
            failures += 1
            print(f"  failed: {error}")
    if failures:
        raise SystemExit(f"{failures} of {len(urls)} articles failed")


if __name__ == "__main__":
    main()
