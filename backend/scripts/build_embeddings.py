import argparse
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.cloth import Cloth
from app.services.integration_tools.fashion_clip import fashion_clip


def main() -> None:
    parser = argparse.ArgumentParser(description="Build missing FashionCLIP image embeddings.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", default=settings.embedding_batch_size, type=int)
    args = parser.parse_args()

    statement = select(Cloth).where(Cloth.embedding.is_(None)).order_by(Cloth.id)
    if args.limit:
        statement = statement.limit(args.limit)

    with SessionLocal() as db:
        clothes = list(db.scalars(statement))
        completed = 0
        for start in range(0, len(clothes), args.batch_size):
            batch = [cloth for cloth in clothes[start : start + args.batch_size] if Path(cloth.image_path).exists()]
            if not batch:
                continue
            embeddings = fashion_clip.encode_images([cloth.image_path for cloth in batch])
            for cloth, embedding in zip(batch, embeddings, strict=True):
                cloth.embedding = embedding
                cloth.embedding_model = settings.fashion_clip_model
            db.commit()
            completed += len(batch)
            print(f"Embedded {completed}/{len(clothes)} images")


if __name__ == "__main__":
    main()
