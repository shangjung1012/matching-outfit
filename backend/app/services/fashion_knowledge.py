import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.styling import (
    ArticleSource,
    ArticleExtraction,
    CollectedArticle,
    KnowledgeRecord,
    OutfitObservation,
)
from app.services.structured_llm import StructuredLLM, local_image_data_url


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


def _record_name(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


class FashionKnowledgeStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.records_dir = self.data_dir / "records"
        self.raw_dir = self.data_dir / "raw"
        self.images_dir = self.data_dir / "images"

    def ensure_dirs(self) -> None:
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def save_collected(self, article: CollectedArticle) -> Path:
        self.ensure_dirs()
        path = self.raw_dir / f"{_record_name(article.source_url)}.json"
        path.write_text(article.model_dump_json(indent=2), encoding="utf-8")
        return path

    def save_record(self, record: KnowledgeRecord) -> Path:
        self.ensure_dirs()
        path = self.records_dir / f"{_record_name(record.article.source_url)}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)
        return path

    def load_records(self) -> list[KnowledgeRecord]:
        if not self.records_dir.exists():
            return []
        records: list[KnowledgeRecord] = []
        for path in sorted(self.records_dir.glob("*.json")):
            records.append(KnowledgeRecord.model_validate_json(path.read_text(encoding="utf-8")))
        return records

    def observations(self) -> list[OutfitObservation]:
        return [observation for record in self.load_records() for observation in record.extraction.observations]


class ArticleKnowledgeExtractor:
    def __init__(self, llm: StructuredLLM, model: str):
        self.llm = llm
        self.model = model

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
            model=self.model,
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
            extraction_model=self.model,
        )


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    latin = set(re.findall(r"[a-z0-9][a-z0-9_-]+", lowered))
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", lowered)
    cjk = {
        run[index : index + 2]
        for run in cjk_runs
        for index in range(max(1, len(run) - 1))
        if run[index : index + 2]
    }
    return latin | cjk


def retrieve_observations(
    query: str, observations: list[OutfitObservation], top_k: int
) -> list[OutfitObservation]:
    query_tokens = _tokens(query)
    ranked: list[tuple[float, OutfitObservation]] = []
    for observation in observations:
        searchable = " ".join(
            [
                observation.summary,
                *observation.occasions,
                *observation.climates,
                *observation.seasons,
                *observation.styles,
                *observation.garments,
                *observation.colors,
                *observation.materials,
                *observation.silhouettes,
                *observation.styling_actions,
                *observation.avoid_when,
            ]
        )
        overlap = len(query_tokens & _tokens(searchable))
        score = overlap * 2.0 + observation.confidence
        if observation.signal_type == "timeless":
            score += 0.25
        ranked.append((score, observation))
    ranked.sort(key=lambda item: item[0], reverse=True)
    positive = [item for item in ranked if item[0] > 0.5]
    return [observation for _, observation in (positive or ranked)[:top_k]]
