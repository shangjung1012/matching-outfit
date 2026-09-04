from app.knowledge.ingestion.article_extractor import (
    ArticleKnowledgeExtractor,
    ArticleTranslationRepair,
    _contains_hangul,
    _substantial_hangul_fields,
)
from app.schemas.fashion_knowledge import ArticleExtraction, OutfitObservation


def extraction(summary: str, evidence: str = "文章依據") -> ArticleExtraction:
    return ArticleExtraction(
        article_summary="文章摘要",
        observations=[
            OutfitObservation(
                summary=summary,
                evidence=evidence,
                signal_type="timeless",
                confidence=0.9,
            )
        ],
    )


def test_detects_korean_in_human_readable_knowledge() -> None:
    assert _contains_hangul(extraction("여름에는 가벼운 소재를 선택한다")) is True


def test_allows_traditional_chinese_knowledge() -> None:
    assert _contains_hangul(extraction("夏季適合選擇輕盈材質")) is False


def test_allows_small_korean_proper_name_residue() -> None:
    result = extraction("可用俐落剪裁搭配 아이유 的簡約造型")

    assert _substantial_hangul_fields(result) == []


def test_reports_fields_with_substantial_korean_text() -> None:
    result = extraction("여름에는 가벼운 소재를 선택한다")

    assert _substantial_hangul_fields(result) == ["observations[0].summary"]


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return ArticleTranslationRepair(
            fields=[
                {
                    "field": "observations[0].summary",
                    "text": "選擇輕盈材質提升舒適度。",
                },
                {
                    "field": "observations[0].evidence",
                    "text": "文章建議夏季選擇透氣單品。",
                },
            ],
        )


def test_translation_repair_sends_only_extracted_readable_text() -> None:
    llm = FakeLLM()
    extractor = ArticleKnowledgeExtractor(llm)
    original = extraction(
        "여름에는 가벼운 소재를 선택한다",
        "기사에서는 통기성이 좋은 옷을 제안한다",
    )
    original.observations[0].styles = ["minimal"]

    repaired, unresolved = extractor._repair_korean_translation(original)

    assert unresolved == []
    assert repaired.observations[0].summary == "選擇輕盈材質提升舒適度。"
    assert repaired.observations[0].styles == ["minimal"]
    assert len(llm.calls) == 1
    request_text = llm.calls[0]["content"][0]["text"]
    assert "observations[0].summary" in request_text
    assert "styles" not in request_text
    assert all(block["type"] == "input_text" for block in llm.calls[0]["content"])


def test_replaces_still_untranslated_evidence_without_discarding_article() -> None:
    result = extraction(
        "選擇輕盈材質提升舒適度。",
        "기사에서는 통기성이 좋은 옷을 제안한다",
    )

    ArticleKnowledgeExtractor._replace_untranslated_evidence(result)

    assert result.observations[0].evidence == (
        "文章內容或圖片支持此搭配觀察：選擇輕盈材質提升舒適度。"
    )
    assert _substantial_hangul_fields(result) == []


class PartialRepairLLM:
    def parse(self, **_kwargs):
        return ArticleTranslationRepair(
            fields=[
                {
                    "field": "observations[0].summary",
                    "text": "以輕盈材質維持夏季清爽感。",
                }
            ],
        )


def test_translation_repair_tolerates_partial_return() -> None:
    extractor = ArticleKnowledgeExtractor(PartialRepairLLM())
    original = extraction(
        "여름에는 가벼운 소재를 선택한다",
        "기사에서는 통기성이 좋은 옷을 제안한다",
    )

    repaired, unresolved = extractor._repair_korean_translation(original)

    assert repaired.observations[0].summary == "以輕盈材質維持夏季清爽感。"
    assert unresolved == ["observations[0].evidence"]


def test_sanitize_untranslated_fields_keeps_record_usable() -> None:
    result = extraction(
        "여름에는 가벼운 소재를 선택한다",
        "기사에서는 통기성이 좋은 옷을 제안한다",
    )

    ArticleKnowledgeExtractor._sanitize_untranslated_fields(result)

    assert _substantial_hangul_fields(result) == []
    assert result.article_summary
    assert result.observations


class TitleTranslationLLM:
    def parse(self, **kwargs):
        schema = kwargs["schema"]
        if schema.__name__ == "ArticleTitleTranslation":
            return schema(title="秋季層次穿搭重點")
        return ArticleTranslationRepair(fields=[])


def test_translates_korean_title_when_needed() -> None:
    extractor = ArticleKnowledgeExtractor(TitleTranslationLLM())

    assert extractor._translate_title_if_needed("가을 레이어드 스타일 팁") == "秋季層次穿搭重點"


class FailingTitleTranslationLLM:
    def parse(self, **_kwargs):
        raise RuntimeError("timeout")


def test_title_translation_falls_back_to_original_on_failure() -> None:
    extractor = ArticleKnowledgeExtractor(FailingTitleTranslationLLM())

    assert extractor._translate_title_if_needed("가을 레이어드 스타일 팁") == "가을 레이어드 스타일 팁"
