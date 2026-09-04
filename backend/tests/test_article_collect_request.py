import pytest
from pydantic import ValidationError

from app.schemas.fashion_knowledge import FashionArticleCollectRequest


@pytest.mark.parametrize("count", [11, 100])
def test_article_collection_accepts_more_than_ten_urls(count):
    urls = [f"https://example.com/article/{index}" for index in range(count)]
    assert FashionArticleCollectRequest(urls=urls).urls == urls


def test_article_collection_still_requires_at_least_one_url():
    with pytest.raises(ValidationError):
        FashionArticleCollectRequest(urls=[])
