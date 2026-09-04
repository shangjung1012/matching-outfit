import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from app.knowledge.ingestion.article_collector import ArticleCollector


@dataclass(frozen=True)
class FashionKnowledgeSource:
    key: str
    name: str
    index_url: str
    audience: str
    article_path_pattern: re.Pattern[str]
    page_url_template: str
    excluded_context_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoveredArticle:
    url: str
    published_at: datetime | None = None


@dataclass(frozen=True)
class ArticleDiscoveryBatch:
    articles: list[DiscoveredArticle]
    skipped_existing: int
    errors: dict[str, str]


SOURCES = (
    FashionKnowledgeSource(
        key="elle_tw",
        name="ELLE Taiwan 穿搭趨勢",
        index_url="https://www.elle.com/tw/fashion/street-snap/",
        audience="women",
        article_path_pattern=re.compile(r"^/tw/fashion/.+/(?:a|g)\d+/.+/?$"),
        page_url_template="https://www.elle.com/tw/fashion/street-snap/?page={page}",
    ),
    FashionKnowledgeSource(
        key="gq_tw",
        name="GQ Taiwan 穿搭指南",
        index_url="https://www.gq.com.tw/tag/%E7%A9%BF%E6%90%AD",
        audience="men",
        article_path_pattern=re.compile(r"^/(?:article|galerie)/[^/]+/?$"),
        page_url_template="https://www.gq.com.tw/tag/%E7%A9%BF%E6%90%AD?page={page}",
    ),
    FashionKnowledgeSource(
        key="marie_claire_kr",
        name="Marie Claire Korea Fashion",
        index_url="https://www.marieclairekorea.com/fashion/",
        audience="women",
        article_path_pattern=re.compile(r"^/fashion/\d{4}/\d{2}/[^/]+/?$"),
        page_url_template="https://www.marieclairekorea.com/fashion/page/{page}/",
        excluded_context_terms=("Jewelry&Watch", "Pictorial"),
    ),
    FashionKnowledgeSource(
        key="gq_kr",
        name="GQ Korea Fashion Item",
        index_url="https://www.gqkorea.co.kr/style/item/",
        audience="men",
        article_path_pattern=re.compile(r"^/\d{4}/\d{2}/\d{2}/[^/]+/?$"),
        page_url_template="https://www.gqkorea.co.kr/style/item/page/{page}/",
    ),
)
SOURCE_BY_KEY = {source.key: source for source in SOURCES}
AUTO_DISCOVERY_MAX_PAGES = 60


def normalize_article_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/")
    return urlunparse(("https", host, path, "", "", ""))


def parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        pass
    patterns = (
        r"(?P<year>20\d{2})[年./-]\s*(?P<month>\d{1,2})[月./-]\s*(?P<day>\d{1,2})日?",
        r"(?P<year>20\d{2})/(?P<month>\d{1,2})/(?P<day>\d{1,2})",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            try:
                return datetime(
                    int(match.group("year")),
                    int(match.group("month")),
                    int(match.group("day")),
                    tzinfo=timezone.utc,
                )
            except ValueError:
                return None
    return None


def _published_at_from_anchor(anchor: Tag, article_url: str) -> datetime | None:
    url_date = parse_published_at(urlparse(article_url).path)
    if url_date:
        return url_date
    current = anchor
    # The date is normally inside the link card. Avoid climbing into the full list,
    # where a neighbouring article's date could be mistaken for this article's date.
    for _ in range(3):
        if current is None:
            break
        dated_element = current.select_one("time[datetime], [datetime]")
        if dated_element is not None:
            parsed = parse_published_at(str(dated_element.get("datetime", "")))
            if parsed:
                return parsed
        parsed = parse_published_at(current.get_text(" ", strip=True))
        if parsed:
            return parsed
        current = current.parent
    return None


class ArticleDiscovery:
    def __init__(self, collector: ArticleCollector):
        self.collector = collector

    def discover(
        self, source: FashionKnowledgeSource, *, page_limit: int = 0
    ) -> list[DiscoveredArticle]:
        candidates: dict[str, tuple[DiscoveredArticle, list[str]]] = {}
        max_pages = page_limit if page_limit > 0 else AUTO_DISCOVERY_MAX_PAGES
        for page in range(1, max_pages + 1):
            page_url = (
                source.index_url
                if page == 1
                else source.page_url_template.format(page=page)
            )
            html, final_url = self.collector.fetch_html(page_url)
            soup = BeautifulSoup(html, "html.parser")
            expected_host = (urlparse(final_url).hostname or "").lower().removeprefix(
                "www."
            )
            page_added = 0
            for anchor in soup.select("a[href]"):
                absolute = urljoin(final_url, str(anchor.get("href", "")))
                parsed = urlparse(absolute)
                host = (parsed.hostname or "").lower().removeprefix("www.")
                if host != expected_host or not source.article_path_pattern.match(parsed.path):
                    continue
                normalized = normalize_article_url(absolute)
                clean_url = absolute.split("#", 1)[0].split("?", 1)[0]
                published_at = _published_at_from_anchor(anchor, clean_url)
                if normalized not in candidates:
                    candidates[normalized] = (
                        DiscoveredArticle(clean_url, published_at),
                        [],
                    )
                    page_added += 1
                elif candidates[normalized][0].published_at is None and published_at:
                    candidates[normalized] = (
                        DiscoveredArticle(clean_url, published_at),
                        candidates[normalized][1],
                    )
                context = anchor.get_text(" ", strip=True)
                if anchor.parent and anchor.parent.parent:
                    context += " " + anchor.parent.parent.get_text(" ", strip=True)
                candidates[normalized][1].append(context)
            # In auto mode, stop when the next page yields no unseen article link.
            if page_limit <= 0 and page_added == 0:
                break
        discovered: list[DiscoveredArticle] = []
        for article, contexts in candidates.values():
            combined_context = " ".join(contexts)
            if any(term in combined_context for term in source.excluded_context_terms):
                continue
            discovered.append(article)
        minimum = datetime.min.replace(tzinfo=timezone.utc)
        return sorted(
            discovered,
            key=lambda article: article.published_at or minimum,
            reverse=True,
        )


def discover_new_articles(
    discovery: ArticleDiscovery,
    sources: list[FashionKnowledgeSource],
    known_urls: set[str],
    *,
    page_limit: int,
    per_source_limit: int,
    max_articles: int,
) -> ArticleDiscoveryBatch:
    normalized_known = {normalize_article_url(url) for url in known_urls}
    candidates: list[DiscoveredArticle] = []
    skipped_existing = 0
    errors: dict[str, str] = {}
    for source in sources:
        try:
            articles = discovery.discover(source, page_limit=page_limit)
        except Exception as error:
            errors[source.key] = str(error)
            continue
        source_added = 0
        for article in articles:
            normalized = normalize_article_url(article.url)
            if normalized in normalized_known:
                skipped_existing += 1
                continue
            normalized_known.add(normalized)
            candidates.append(article)
            source_added += 1
            if source_added >= per_source_limit:
                break
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    candidates.sort(
        key=lambda article: article.published_at or minimum,
        reverse=True,
    )
    return ArticleDiscoveryBatch(
        articles=candidates[:max_articles],
        skipped_existing=skipped_existing,
        errors=errors,
    )
