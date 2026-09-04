import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.fashion_knowledge import (
    ArticleSource,
    ArticleExtraction,
    CollectedArticle,
    KnowledgeRecord,
)
from app.services.integration_tools.llm import LLM, local_image_data_url

PROMPTS_DIR = Path(__file__).parents[2] / "services" / "prompts"
EXTRACTION_SYSTEM_PROMPT = (PROMPTS_DIR / "ArticleExtractor.txt").read_text(
    encoding="utf-8"
).strip()


class ArticleKnowledgeExtractor:
    def __init__(self, llm: LLM):
        self.llm = llm

    def extract(self, article: CollectedArticle) -> KnowledgeRecord:
        article_payload = {
            "source": article.source_name,
            "url": article.source_url,
            "title": article.title,
            "published_at": article.published_at,
            "text": article.text[:24000],
            "images": [
                {"index": index, "alt": image.alt, "caption": image.caption}
                for index, image in enumerate(article.images[:4])
            ],
        }
        content: list[dict] = [
            {
                "type": "input_text",
                "text": "Extract fashion observations from this article:\n"
                + json.dumps(article_payload, ensure_ascii=False),
            }
        ]
        for index, image in enumerate(article.images[:4]):
            content.append({"type": "input_text", "text": f"Article image {index}:"})
            image_url = local_image_data_url(image.local_path) if image.local_path else image.url
            content.append({"type": "input_image", "image_url": image_url, "detail": "low"})
        extraction = self.llm.parse(
            stage="article_extraction",
            instructions=EXTRACTION_SYSTEM_PROMPT,
            content=content,
            schema=ArticleExtraction,
        )
        for index, observation in enumerate(extraction.observations):
            digest = hashlib.sha256(
                f"{article.source_url}:{index}:{observation.summary}".encode("utf-8")
            ).hexdigest()[:12]
            observation.observation_id = f"obs_{digest}"
            observation.source_url = article.source_url
            observation.source_name = article.source_name
            observation.source_title = article.title
            observation.published_at = article.published_at
        return KnowledgeRecord(
            article=ArticleSource(
                source_url=article.source_url,
                source_name=article.source_name,
                title=article.title,
                author=article.author,
                published_at=article.published_at,
                collected_at=article.collected_at,
                language=article.language,
            ),
            extraction=extraction,
            extracted_at=datetime.now(timezone.utc),
            extraction_model=self.llm.model_for("article_extraction"),
        )
