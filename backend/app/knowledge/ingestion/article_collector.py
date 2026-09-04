"""Offline HTML article collection for fashion-knowledge ingestion."""

import hashlib
import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup, Tag

from app.schemas.styling import ArticleBlock, ArticleImage, CollectedArticle


NOISE_SELECTOR = ",".join(
    [
        "script",
        "style",
        "noscript",
        "nav",
        "footer",
        "aside",
        "form",
        "[aria-hidden='true']",
        "[class*='advert']",
        "[class*='related']",
        "[class*='recommend']",
        "[class*='newsletter']",
        "[class*='social']",
    ]
)


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _first_meta(soup: BeautifulSoup, *selectors: tuple[str, str]) -> str | None:
    for attribute, value in selectors:
        element = soup.find("meta", attrs={attribute: value})
        if element and element.get("content"):
            return _clean(str(element["content"]))
    return None


def _json_ld_articles(soup: BeautifulSoup) -> list[dict]:
    results: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            graph = candidate.get("@graph", [])
            candidates_to_check = [candidate, *(graph if isinstance(graph, list) else [])]
            for item in candidates_to_check:
                item_type = item.get("@type", "") if isinstance(item, dict) else ""
                item_types = item_type if isinstance(item_type, list) else [item_type]
                if any(value in {"Article", "NewsArticle", "BlogPosting"} for value in item_types):
                    results.append(item)
    return results


def _image_url(tag: Tag, base_url: str) -> str | None:
    raw = (
        tag.get("data-src")
        or tag.get("data-lazy-src")
        or tag.get("data-original")
        or tag.get("src")
    )
    if not raw and tag.get("srcset"):
        raw = str(tag["srcset"]).split(",")[-1].strip().split(" ")[0]
    if not raw or str(raw).startswith(("data:", "blob:")):
        return None
    url = urljoin(base_url, str(raw))
    lowered = url.lower()
    if any(token in lowered for token in ("logo", "icon", "avatar", "sprite", ".svg")):
        return None
    return url


class ArticleCollector:
    def __init__(self, allowed_domains: set[str], user_agent: str, timeout: float = 25.0):
        self.allowed_domains = {domain.lower() for domain in allowed_domains}
        self.user_agent = user_agent
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7"},
        )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only public http(s) article URLs are supported")
        if parsed.hostname.lower() not in self.allowed_domains:
            raise ValueError(f"Article domain is not allowlisted: {parsed.hostname}")

    def _check_robots(self, url: str) -> None:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        response = self.client.get(robots_url)
        if response.status_code != 200:
            return
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        if not parser.can_fetch(self.user_agent, url):
            raise PermissionError(f"robots.txt does not allow collection of {url}")

    def collect(self, url: str, *, check_robots: bool = True) -> CollectedArticle:
        self._validate_url(url)
        if check_robots:
            self._check_robots(url)
        response = self.client.get(url)
        response.raise_for_status()
        self._validate_url(str(response.url))
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type:
            raise ValueError(f"Expected an HTML article, received {content_type or 'unknown content'}")
        return self.parse_html(response.text, str(response.url))

    def parse_html(self, html: str, source_url: str) -> CollectedArticle:
        soup = BeautifulSoup(html, "html.parser")
        json_ld = _json_ld_articles(soup)
        structured = json_ld[0] if json_ld else {}
        title = _clean(
            structured.get("headline")
            or _first_meta(soup, ("property", "og:title"), ("name", "twitter:title"))
            or (soup.find("h1").get_text(" ") if soup.find("h1") else "")
            or (soup.title.get_text(" ") if soup.title else "")
        )
        if not title:
            raise ValueError("Could not identify an article title")

        root = (
            soup.select_one("[itemprop='articleBody']")
            or soup.find("article")
            or soup.select_one("main")
        )
        if root is None:
            raise ValueError("Could not identify the article body")
        for noise in root.select(NOISE_SELECTOR):
            noise.decompose()

        images: list[ArticleImage] = []
        image_index_by_tag: dict[int, int] = {}
        seen_urls: set[str] = set()
        for image_tag in root.find_all("img"):
            image_url = _image_url(image_tag, source_url)
            if not image_url or image_url in seen_urls:
                continue
            width = str(image_tag.get("width", ""))
            height = str(image_tag.get("height", ""))
            if width.isdigit() and height.isdigit() and (int(width) < 250 or int(height) < 250):
                continue
            figure = image_tag.find_parent("figure")
            caption_tag = figure.find("figcaption") if figure else None
            image_index_by_tag[id(image_tag)] = len(images)
            images.append(
                ArticleImage(
                    url=image_url,
                    alt=_clean(str(image_tag.get("alt", ""))),
                    caption=_clean(caption_tag.get_text(" ") if caption_tag else ""),
                )
            )
            seen_urls.add(image_url)
            if len(images) >= 20:
                break

        blocks: list[ArticleBlock] = []
        heading = ""
        paragraphs: list[str] = []
        block_images: list[int] = []

        def flush() -> None:
            nonlocal paragraphs, block_images
            text = "\n".join(paragraphs).strip()
            if text:
                blocks.append(
                    ArticleBlock(
                        heading=heading,
                        text=text,
                        image_indexes=list(dict.fromkeys(block_images)),
                    )
                )
            paragraphs = []
            block_images = []

        for element in root.find_all(["h2", "h3", "p", "figure"]):
            if element.name in {"h2", "h3"}:
                flush()
                heading = _clean(element.get_text(" "))
            elif element.name == "p":
                value = _clean(element.get_text(" "))
                if len(value) >= 25:
                    paragraphs.append(value)
            else:
                for image_tag in element.find_all("img"):
                    index = image_index_by_tag.get(id(image_tag))
                    if index is not None:
                        block_images.append(index)
        flush()

        if not blocks:
            fallback = [
                _clean(paragraph.get_text(" "))
                for paragraph in root.find_all("p")
                if len(_clean(paragraph.get_text(" "))) >= 25
            ]
            if fallback:
                blocks = [ArticleBlock(text="\n".join(fallback), image_indexes=[])]
        article_text = "\n\n".join(
            f"{block.heading}\n{block.text}" if block.heading else block.text for block in blocks
        )
        if len(article_text) < 80:
            raise ValueError("The page did not contain enough article text")

        author_data = structured.get("author")
        if isinstance(author_data, list):
            author = ", ".join(
                str(item.get("name", "")) if isinstance(item, dict) else str(item)
                for item in author_data
            )
        elif isinstance(author_data, dict):
            author = str(author_data.get("name", ""))
        else:
            author = str(author_data or "")
        hostname = urlparse(source_url).hostname or "unknown"
        published_at = structured.get("datePublished")
        if not published_at:
            published_at = _first_meta(soup, ("property", "article:published_time"))
        return CollectedArticle(
            source_url=source_url,
            source_name=hostname.removeprefix("www."),
            title=title,
            author=_clean(author) or _first_meta(soup, ("name", "author")),
            published_at=_clean(str(published_at or "")) or None,
            collected_at=datetime.now(timezone.utc),
            language=(soup.html.get("lang") if soup.html else None),
            text=article_text,
            blocks=blocks,
            images=images,
        )

    def download_images(
        self, article: CollectedArticle, output_dir: Path, *, max_images: int = 4
    ) -> CollectedArticle:
        output_dir.mkdir(parents=True, exist_ok=True)
        for image in article.images[:max_images]:
            response = self.client.get(image.url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
            if not content_type.startswith("image/"):
                continue
            suffix = mimetypes.guess_extension(content_type) or Path(urlparse(image.url).path).suffix
            if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                suffix = ".jpg"
            name = hashlib.sha256(image.url.encode("utf-8")).hexdigest()[:16] + suffix
            path = output_dir / name
            path.write_bytes(response.content)
            image.local_path = str(path)
        return article
