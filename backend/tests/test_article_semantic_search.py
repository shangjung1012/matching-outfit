from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from fastapi import HTTPException

from app.api import fashion_knowledge_admin as api
from app.knowledge.article_search import article_match_query, ensure_article_embeddings


class Embedder:
    model = "test-model"
    dimensions = 512
    def __init__(self): self.inputs = []
    def encode(self, texts):
        self.inputs.extend(texts)
        return [[0.1] * 512 for _ in texts]


class DB:
    def __init__(self, article): self.article = article; self.commits = 0; self.rollbacks = 0
    def scalars(self, query):
        rows = [self.article] if 'FROM fashion_articles' in str(query) else []
        return SimpleNamespace(all=lambda: rows)
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


def test_title_without_observations_is_indexed_once_and_refreshes_changed_title():
    article = SimpleNamespace(title="女團造型", article_summary="棕白色搭配", search_embedding=None,
                              search_embedding_model=None, search_embedding_text=None)
    db, embedder = DB(article), Embedder()
    ensure_article_embeddings(db, embedder)
    assert "女團造型" in embedder.inputs[0]
    assert article.search_embedding_model == embedder.model
    ensure_article_embeddings(db, embedder)
    assert len(embedder.inputs) == 1
    article.title = "新標題"
    ensure_article_embeddings(db, embedder)
    assert len(embedder.inputs) == 2 and "新標題" in embedder.inputs[-1]


def test_match_sql_merges_both_sources_and_deduplicates_articles():
    sql = str(select(article_match_query([0.1] * 512, "test-model")).compile(dialect=postgresql.dialect()))
    assert "UNION ALL" in sql and "row_number() OVER (PARTITION BY" in sql
    assert "fashion_articles.search_embedding" in sql
    assert "fashion_observations.embedding" in sql
    assert "embedding_model" in sql and "is_active IS true" in sql
    assert "position =" in sql and "similarity >=" in sql


def test_search_api_uses_embedding_and_passes_pagination(monkeypatch):
    embedder = Embedder()
    monkeypatch.setattr(api, "TextEmbeddingService", lambda *args: embedder)
    captured = []
    def search(db, text, passed_embedder, **kwargs):
        captured.append((text, passed_embedder, kwargs))
        return [], 7
    monkeypatch.setattr(api, "search_articles", search)
    result = api.list_articles(search="  復古女團  ", limit=10, offset=20, db=object())
    assert result.total == 7
    assert captured == [("復古女團", embedder, {"limit": 10, "offset": 20})]


def test_embedding_failure_is_reported_not_silently_changed_to_keyword_search(monkeypatch):
    def fail(*args): raise RuntimeError("missing key")
    monkeypatch.setattr(api, "TextEmbeddingService", fail)
    with pytest.raises(HTTPException) as error:
        api.list_articles(search="女團", limit=50, offset=0, db=object())
    assert error.value.status_code == 503
    assert "語意搜尋不可用" in error.value.detail
