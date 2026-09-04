import hashlib
import json
from datetime import datetime, timezone

from app.schemas.styling import (
    ArticleSource,
    ArticleExtraction,
    CollectedArticle,
    KnowledgeRecord,
)
from app.services.integration_tools.llm import LLM, local_image_data_url


EXTRACTION_SYSTEM_PROMPT = """
You are a fashion knowledge editor. Convert one magazine article and its images into
small, reusable outfit observations for a retrieval system.

Ground every observation in supplied text or a visible image. Never invent a garment,
color, material, occasion, or rule. Treat one editorial look as an example, not a
universal truth. Separate durable coordination principles from current trends and from
one-off editorial examples using signal_type. Prefer concrete relationships such as
color balance, proportions, layering, formality, texture, and styling actions. Do not
extract shopping copy, prices, brand promotion, celebrity biography, or duplicated
observations. Keep the evidence short and paraphrased. Use concise Traditional Chinese
for summaries and evidence; tags should be short normalized Chinese or English terms.
Set audiences to men, women, or unisex only when supported by the article context or
visible garments. Use unisex for genuinely gender-independent coordination principles.
Return at most 12 observations. It is valid to return fewer when evidence is weak.
""".strip()


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
