import argparse

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.fashion_knowledge import FashionKnowledgeStore
from app.services.fashion_knowledge_repository import import_knowledge_records
from app.services.text_embeddings import TextEmbeddingService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import extracted fashion observations into PostgreSQL and build embeddings."
    )
    parser.add_argument("--refresh-embeddings", action="store_true")
    args = parser.parse_args()

    records = FashionKnowledgeStore(settings.article_data_dir).load_records()
    if not records:
        raise SystemExit("No extracted fashion knowledge records were found")
    embedder = TextEmbeddingService(
        settings.openai_api_key,
        settings.knowledge_embedding_model,
        settings.knowledge_embedding_dimensions,
    )
    with SessionLocal() as db:
        articles, observations, embedded = import_knowledge_records(
            db, records, embedder, refresh_embeddings=args.refresh_embeddings
        )
    print(
        f"Imported {articles} articles and {observations} observations; "
        f"generated {embedded} embeddings with {embedder.model}."
    )


if __name__ == "__main__":
    main()
