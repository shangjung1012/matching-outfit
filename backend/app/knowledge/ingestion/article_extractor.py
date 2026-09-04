import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field

from app.schemas.fashion_knowledge import (
    ArticleSource,
    ArticleExtraction,
    CollectedArticle,
    KnowledgeRecord,
    StrictModel,
)
from app.services.integration_tools.llm import LLM, local_image_data_url

PROMPTS_DIR = Path(__file__).parents[2] / "services" / "prompts"
EXTRACTION_SYSTEM_PROMPT = (PROMPTS_DIR / "ArticleExtractor.txt").read_text(
    encoding="utf-8"
).strip()
TRANSLATION_REPAIR_SYSTEM_PROMPT = (
    PROMPTS_DIR / "ArticleTranslationRepair.txt"
).read_text(encoding="utf-8").strip()


class FieldTranslationRepair(StrictModel):
    field: str
    text: str


class ArticleTranslationRepair(StrictModel):
    fields: list[FieldTranslationRepair] = Field(default_factory=list)


class ArticleTitleTranslation(StrictModel):
    title: str


def _human_readable_fields(extraction: ArticleExtraction) -> list[tuple[str, str]]:
    fields = [("article_summary", extraction.article_summary)]
    fields.extend(
        (f"extraction_notes[{index}]", value)
        for index, value in enumerate(extraction.extraction_notes)
    )
    for index, observation in enumerate(extraction.observations):
        fields.extend(
            (
                (f"observations[{index}].summary", observation.summary),
                (f"observations[{index}].evidence", observation.evidence),
            )
        )
    return fields


def _substantial_hangul_fields(extraction: ArticleExtraction) -> list[str]:
    issues: list[str] = []
    for field, value in _human_readable_fields(extraction):
        hangul_count = len(re.findall(r"[\uac00-\ud7af]", value))
        readable_count = len(re.findall(r"[A-Za-z\u3400-\u9fff\uac00-\ud7af]", value))
        hangul_ratio = hangul_count / readable_count if readable_count else 0.0
        # A few remaining syllables are commonly a person's or brand's proper name.
        # Reject only content that still contains a meaningful Korean phrase.
        if hangul_count >= 8 or (hangul_count >= 4 and hangul_ratio >= 0.5):
            issues.append(field)
    return issues


def _has_substantial_hangul(text: str) -> bool:
    hangul_count = len(re.findall(r"[\uac00-\ud7af]", text))
    readable_count = len(re.findall(r"[A-Za-z\u3400-\u9fff\uac00-\ud7af]", text))
    hangul_ratio = hangul_count / readable_count if readable_count else 0.0
    return hangul_count >= 8 or (hangul_count >= 4 and hangul_ratio >= 0.5)


def _contains_hangul(extraction: ArticleExtraction) -> bool:
    return any(
        re.search(r"[\uac00-\ud7af]", value)
        for _, value in _human_readable_fields(extraction)
    )


class ArticleKnowledgeExtractor:
    def __init__(self, llm: LLM):
        self.llm = llm

    def _translate_title_if_needed(self, title: str) -> str:
        if not re.search(r"[\uac00-\ud7af]", title):
            return title
        try:
            translated = self.llm.parse(
                stage="article_extraction",
                instructions=(
                    "Translate the given fashion article title into concise Traditional "
                    "Chinese. Keep only visually reusable styling meaning and avoid proper "
                    "names when possible. Return JSON with exactly one field: title."
                ),
                content=[
                    {
                        "type": "input_text",
                        "text": json.dumps({"title": title}, ensure_ascii=False),
                    }
                ],
                schema=ArticleTitleTranslation,
            )
            cleaned = translated.title.strip()
            return cleaned or title
        except Exception:
            return title

    def _repair_korean_translation(
        self,
        extraction: ArticleExtraction,
        fields_to_repair: list[str] | None = None,
    ) -> tuple[ArticleExtraction, list[str]]:
        readable_fields = dict(_human_readable_fields(extraction))
        requested_fields = fields_to_repair or [
            field
            for field, value in readable_fields.items()
            if re.search(r"[\uac00-\ud7af]", value)
        ]
        if not requested_fields:
            return extraction, []
        payload = {
            "fields": [
                {"field": field, "text": readable_fields[field]}
                for field in requested_fields
            ]
        }
        repaired = self.llm.parse(
            stage="article_extraction",
            instructions=TRANSLATION_REPAIR_SYSTEM_PROMPT,
            content=[
                {
                    "type": "input_text",
                    "text": json.dumps(payload, ensure_ascii=False),
                }
            ],
            schema=ArticleTranslationRepair,
        )
        repaired_by_field = {
            item.field: item.text
            for item in repaired.fields
            if item.field in requested_fields and item.text.strip()
        }
        for field, value in repaired_by_field.items():
            if field == "article_summary":
                extraction.article_summary = value
                continue
            note_match = re.fullmatch(r"extraction_notes\[(\d+)]", field)
            if note_match:
                extraction.extraction_notes[int(note_match.group(1))] = value
                continue
            observation_match = re.fullmatch(
                r"observations\[(\d+)]\.(summary|evidence)", field
            )
            if observation_match:
                observation = extraction.observations[int(observation_match.group(1))]
                setattr(observation, observation_match.group(2), value)
                continue
        unresolved = [field for field in requested_fields if field not in repaired_by_field]
        return extraction, unresolved

    @staticmethod
    def _sanitize_untranslated_fields(extraction: ArticleExtraction) -> None:
        issue_set = set(_substantial_hangul_fields(extraction))
        if not issue_set:
            return

        extraction.extraction_notes = [
            note
            for index, note in enumerate(extraction.extraction_notes)
            if f"extraction_notes[{index}]" not in issue_set
            and not _has_substantial_hangul(note)
        ]

        cleaned_observations = []
        for index, observation in enumerate(extraction.observations):
            summary_key = f"observations[{index}].summary"
            evidence_key = f"observations[{index}].evidence"

            if summary_key in issue_set or _has_substantial_hangul(observation.summary):
                if not _has_substantial_hangul(observation.evidence):
                    observation.summary = observation.evidence
                else:
                    observation.summary = "可重複使用的穿搭重點：協調版型、比例與材質。"

            if evidence_key in issue_set or _has_substantial_hangul(observation.evidence):
                observation.evidence = (
                    f"文章內容或圖片支持此搭配觀察：{observation.summary}"
                )

            if _has_substantial_hangul(observation.summary):
                continue
            cleaned_observations.append(observation)

        extraction.observations = cleaned_observations

        if _has_substantial_hangul(extraction.article_summary):
            extraction.article_summary = (
                extraction.observations[0].summary
                if extraction.observations
                else "此篇文章提供可重複使用的穿搭重點。"
            )

    @staticmethod
    def _replace_untranslated_evidence(extraction: ArticleExtraction) -> None:
        issue_set = set(_substantial_hangul_fields(extraction))
        extraction.extraction_notes = [
            note
            for index, note in enumerate(extraction.extraction_notes)
            if f"extraction_notes[{index}]" not in issue_set
        ]
        for index, observation in enumerate(extraction.observations):
            if f"observations[{index}].evidence" in issue_set:
                observation.evidence = (
                    f"文章內容或圖片支持此搭配觀察：{observation.summary}"
                )

    def extract(self, article: CollectedArticle) -> KnowledgeRecord:
        translated_title = self._translate_title_if_needed(article.title)
        article_payload = {
            "source": article.source_name,
            "url": article.source_url,
            "title": translated_title,
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
        if _contains_hangul(extraction):
            extraction, _ = self._repair_korean_translation(extraction)
        hangul_issues = _substantial_hangul_fields(extraction)
        if hangul_issues:
            extraction, unresolved = self._repair_korean_translation(
                extraction, hangul_issues
            )
            if unresolved:
                extraction, _ = self._repair_korean_translation(extraction, unresolved)
            self._replace_untranslated_evidence(extraction)
            self._sanitize_untranslated_fields(extraction)
            hangul_issues = _substantial_hangul_fields(extraction)
        if hangul_issues:
            self._sanitize_untranslated_fields(extraction)
        for index, observation in enumerate(extraction.observations):
            digest = hashlib.sha256(
                f"{article.source_url}:{index}:{observation.summary}".encode("utf-8")
            ).hexdigest()[:12]
            observation.observation_id = f"obs_{digest}"
            observation.source_url = article.source_url
            observation.source_name = article.source_name
            observation.source_title = translated_title
            observation.published_at = article.published_at
        return KnowledgeRecord(
            article=ArticleSource(
                source_url=article.source_url,
                source_name=article.source_name,
                title=translated_title,
                author=article.author,
                published_at=article.published_at,
                collected_at=article.collected_at,
                language=article.language,
            ),
            extraction=extraction,
            extracted_at=datetime.now(timezone.utc),
            extraction_model=self.llm.model_for("article_extraction"),
        )
