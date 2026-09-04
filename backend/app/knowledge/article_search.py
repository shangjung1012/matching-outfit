"""Semantic article browsing: merge title/summary and observation vector matches."""

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.orm import selectinload

from app.models.fashion_knowledge import FashionArticle, FashionObservation
from app.knowledge.ingestion.db_importer import observation_embedding_text


def article_embedding_text(article):
    return f"title: {article.title}\nsummary: {article.article_summary}".strip()


def ensure_article_embeddings(db, embedder):
    if embedder.dimensions != 512:
        raise ValueError("文章索引需要 512 維 embedding")
    articles = db.scalars(select(FashionArticle)).all()
    pending = [(article, article_embedding_text(article)) for article in articles
               if article.search_embedding is None or article.search_embedding_model != embedder.model
               or article.search_embedding_text != article_embedding_text(article)]
    observations = db.scalars(select(FashionObservation).where(FashionObservation.is_active.is_(True))).all()
    missing_knowledge = [(row, observation_embedding_text(row, row.audiences or [])) for row in observations
                         if row.embedding is None or row.embedding_model != embedder.model]
    if not pending and not missing_knowledge:
        return
    try:
        vectors = embedder.encode([text for _, text in pending + missing_knowledge])
        for (article, text), vector in zip(pending, vectors[:len(pending)], strict=True):
            article.search_embedding = vector
            article.search_embedding_model = embedder.model
            article.search_embedding_text = text
        for (row, _), vector in zip(missing_knowledge, vectors[len(pending):], strict=True):
            row.embedding = vector
            row.embedding_model = embedder.model
        db.commit()
    except Exception:
        db.rollback()
        raise


def article_match_query(vector, model, min_similarity=0.2):
    title_matches = select(
        FashionArticle.id.label("article_id"),
        (1 - FashionArticle.search_embedding.cosine_distance(vector)).label("similarity"),
        literal("title_summary").label("match_kind"), FashionArticle.title.label("match_text"),
    ).where(FashionArticle.search_embedding.is_not(None), FashionArticle.search_embedding_model == model)
    knowledge_matches = select(
        FashionObservation.article_id.label("article_id"),
        (1 - FashionObservation.embedding.cosine_distance(vector)).label("similarity"),
        literal("knowledge").label("match_kind"), FashionObservation.summary.label("match_text"),
    ).where(FashionObservation.embedding.is_not(None), FashionObservation.embedding_model == model,
            FashionObservation.is_active.is_(True))
    candidates = union_all(title_matches, knowledge_matches).subquery()
    ranked = select(candidates, func.row_number().over(
        partition_by=candidates.c.article_id,
        order_by=(candidates.c.similarity.desc(), candidates.c.match_kind, candidates.c.match_text),
    ).label("position")).subquery()
    return select(ranked).where(ranked.c.position == 1, ranked.c.similarity >= min_similarity).subquery()


def search_articles(db, search, embedder, *, limit=50, offset=0):
    ensure_article_embeddings(db, embedder)
    vector = embedder.encode([search])[0]
    matches = article_match_query(vector, embedder.model)
    total = db.scalar(select(func.count()).select_from(matches)) or 0
    rows = db.execute(select(FashionArticle, matches.c.similarity, matches.c.match_kind, matches.c.match_text)
                      .join(matches, matches.c.article_id == FashionArticle.id)
                      .options(selectinload(FashionArticle.observations))
                      .order_by(matches.c.similarity.desc(), FashionArticle.id.desc())
                      .offset(offset).limit(limit)).all()
    return rows, total
