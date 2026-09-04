from app.knowledge.ingestion.article_discovery import (
    SOURCE_BY_KEY,
    ArticleDiscovery,
    normalize_article_url,
    parse_published_at,
)


class FakeCollector:
    def __init__(self, html: str | dict[str, str], final_url: str):
        self.html = html
        self.final_url = final_url
        self.requested_urls: list[str] = []

    def fetch_html(self, url: str, *, check_robots: bool = True) -> tuple[str, str]:
        self.requested_urls.append(url)
        html = self.html[url] if isinstance(self.html, dict) else self.html
        return html, url if isinstance(self.html, dict) else self.final_url


def test_discovers_only_matching_same_site_article_links() -> None:
    html = """
    <a href="/tw/fashion/street-snap/g73600209/look/">valid</a>
    <a href="/tw/fashion/street-snap/">category</a>
    <a href="https://example.com/tw/fashion/street-snap/g123/look/">external</a>
    <a href="/tw/fashion/street-snap/g73600209/look/?utm_source=x">duplicate</a>
    """
    collector = FakeCollector(html, "https://www.elle.com/tw/fashion/street-snap/")

    links = ArticleDiscovery(collector).discover(SOURCE_BY_KEY["elle_tw"])

    assert [article.url for article in links] == [
        "https://www.elle.com/tw/fashion/street-snap/g73600209/look/"
    ]


def test_normalize_article_url_removes_tracking_and_www() -> None:
    assert normalize_article_url("http://www.gq.com.tw/article/look/?utm_source=x#top") == (
        "https://gq.com.tw/article/look"
    )


def test_discovers_multiple_pages_and_sorts_by_published_at() -> None:
    source = SOURCE_BY_KEY["gq_tw"]
    pages = {
        source.index_url: """
            <article><a href="/article/older">Older</a><time datetime="2026-08-01"></time></article>
        """,
        source.page_url_template.format(page=2): """
            <article><a href="/article/newer">Newer</a><time datetime="2026-09-01"></time></article>
        """,
    }
    collector = FakeCollector(pages, source.index_url)

    articles = ArticleDiscovery(collector).discover(source, page_limit=2)

    assert [article.url for article in articles] == [
        "https://www.gq.com.tw/article/newer",
        "https://www.gq.com.tw/article/older",
    ]
    assert collector.requested_urls == list(pages)


def test_auto_page_limit_scans_until_page_without_new_links() -> None:
    source = SOURCE_BY_KEY["gq_tw"]
    pages = {
        source.index_url: """
            <article><a href="/article/new-a">A</a><time datetime="2026-09-02"></time></article>
        """,
        source.page_url_template.format(page=2): """
            <article><a href="/article/new-b">B</a><time datetime="2026-09-01"></time></article>
        """,
        source.page_url_template.format(page=3): """
            <article><a href="/article/new-b">B duplicate</a></article>
        """,
    }
    collector = FakeCollector(pages, source.index_url)

    articles = ArticleDiscovery(collector).discover(source, page_limit=0)

    assert [article.url for article in articles] == [
        "https://www.gq.com.tw/article/new-a",
        "https://www.gq.com.tw/article/new-b",
    ]
    assert collector.requested_urls == list(pages)


def test_parse_published_at_supports_site_date_formats() -> None:
    assert parse_published_at("2026年8月31日").date().isoformat() == "2026-08-31"
    assert parse_published_at("2026.09.04 by editor").date().isoformat() == "2026-09-04"
    assert parse_published_at("/2026/08/28/article/").date().isoformat() == "2026-08-28"
