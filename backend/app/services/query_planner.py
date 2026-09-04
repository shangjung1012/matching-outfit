import json
import logging
import re
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4
from pathlib import Path

from pydantic import Field

from app.models.user_preference import UserHardRule, UserStylePreference
from app.core.config import settings
from app.schemas.fashion_knowledge import StrictModel, OutfitObservation
from app.schemas.workflow import (
    ChatTurn,
    ClarificationResponse,
    FashionIntent,
    PlanResponse,
    QueryDraft,
    QueryPlanDebug,
    RequirementField,
    RequirementSummary,
    StylingGuide,
)
from app.services.integration_tools.llm import LLM
from app.preferences.context import build_planner_preference_context
from app.services.requirement_context import current_taiwan_context, with_context_defaults

# get system and general prompts for QueryPlanner
PROMPTS_DIR = Path(__file__).parent / "prompts"
QUERY_PLANNER_SYSTEM_PROMPT = (PROMPTS_DIR / "QueryPlanner.txt").read_text(encoding="utf-8").strip()
QUERY_REPAIR_SYSTEM_PROMPT = (PROMPTS_DIR / "QueryPlannerSys.txt").read_text(encoding="utf-8").strip()
REQUIREMENT_COLLECTOR_PROMPT = (PROMPTS_DIR / "RequirementCollector.txt").read_text(
    encoding="utf-8"
).strip()
FASHION_INTENT_INTERPRETER_PROMPT = (
    PROMPTS_DIR / "FashionIntentInterpreter.txt"
).read_text(encoding="utf-8").strip()
logger = logging.getLogger(__name__)
QUERY_ZONES = ("upper_body", "lower_body", "one_piece")
QUERY_COUNTS = {"upper_body": 5, "lower_body": 5, "one_piece": 2}
REQUIREMENT_VALUE_FIELDS = (
    "location",
    "target_date",
    "occasions",
    "seasons",
    "times_of_day",
    "climates",
    "formalities",
    "activities",
    "styles",
    "special_requirements",
    "additional_notes",
)

FALLBACK_QUERIES = {
    "upper_body": (
        "visually coherent versatile relaxed upper-body top",
        "visually coherent versatile structured upper-body top",
        "visually coherent lightweight layered upper-body top",
        "visually coherent clean minimal upper-body top",
        "visually coherent soft draped upper-body top",
    ),
    "lower_body": (
        "visually coherent versatile relaxed lower-body trousers or skirt",
        "visually coherent versatile tailored lower-body trousers or skirt",
        "visually coherent lightweight flowing lower-body trousers or skirt",
        "visually coherent clean minimal lower-body trousers or skirt",
        "visually coherent structured lower-body trousers or skirt",
    ),
    "one_piece": (
        "visually coherent versatile relaxed one-piece dress or jumpsuit",
        "visually coherent versatile structured one-piece dress or jumpsuit",
    ),
}

# 多種顏色統一
COLOR_ALIASES = {
    "black": ("black", "黑色", "黑"),
    "white": ("off white", "ivory", "white", "白色", "米白", "象牙色"),
    "grey": ("charcoal", "gray", "grey", "灰色", "炭灰"),
    "beige": ("beige", "cream", "taupe", "nude", "米色", "奶油色", "裸色"),
    "brown": ("coffee brown", "brown", "tan", "咖啡色", "棕色", "褐色"),
    "blue": ("navy blue", "turquoise blue", "blue", "navy", "藍色", "藍", "海軍藍"),
    "green": ("lime green", "sea green", "green", "olive", "綠色", "綠", "橄欖綠"),
    "red": ("burgundy", "maroon", "red", "紅色", "紅", "酒紅"),
    "pink": ("magenta", "mauve", "pink", "rose", "peach", "粉色", "粉紅", "桃色"),
    "purple": ("lavender", "purple", "紫色", "紫", "薰衣草色"),
    "orange": ("orange", "rust", "橘色", "橙色", "橘"),
    "yellow": ("mustard", "yellow", "黃色", "黃", "芥末黃"),
    "metallic": ("silver", "gold", "bronze", "copper", "銀色", "金色", "古銅色"),
}

REJECTABLE_CONCEPTS = {
    "skirt": (("裙子", "裙裝", "skirt", "skirts"), ("skirt", "skirts", "miniskirt")),
    "dress": (("洋裝", "連身裙", "dress", "dresses"), ("dress", "dresses", "gown")),
    "denim": (("牛仔", "denim", "jean", "jeans"), ("denim", "jean", "jeans")),
    "shorts": (("短褲", "shorts"), ("shorts",)),
    "sleeveless": (("無袖", "sleeveless"), ("sleeveless",)),
    "cropped": (("短版", "露腰", "crop top", "cropped"), ("crop top", "cropped", "crop")),
    "tight": (("緊身", "貼身", "tight", "bodycon"), ("tight", "bodycon", "fitted")),
    "oversized": (("寬鬆", "oversized", "baggy"), ("oversized", "baggy")),
    "stripes": (("條紋", "striped", "stripes"), ("striped", "stripes")),
}

CHINESE_REJECTION_PREFIX = re.compile(
    r"(?:不要|不想(?:要|穿)?|避免|不喜歡|討厭|排除|不能穿)[^，。；,.但而]{0,10}$"
)
ENGLISH_REJECTION_PREFIX = re.compile(
    r"(?:\bno|\bnot|\bavoid|\bwithout|\bdislike|\bhate|\bexclude|"
    r"\bdon['’]?t\s+(?:want|wear))\b(?:\W+\w+){0,4}\W*$",
    flags=re.IGNORECASE,
)


class PlannedCatalogQuery(StrictModel):
    garment_zone: Literal["upper_body", "lower_body", "one_piece"]
    direction_id: str = Field(min_length=1, max_length=24)
    text: str = Field(min_length=3, max_length=240)
    rationale: str = Field(min_length=2, max_length=300)


class KnowledgeQueryDraft(StrictModel):
    cited_observation_ids: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    knowledge_note: str = ""
    context_restrictiveness: Literal["low", "medium", "high"]
    hard_constraints: list[str] = Field(default_factory=list)
    excluded_query_terms: list[str] = Field(default_factory=list)
    aesthetic_direction: list[str] = Field(default_factory=list)
    styling_guide: StylingGuide
    queries: list[PlannedCatalogQuery] = Field(min_length=12, max_length=12)
    planning_note: str


class TagTranslation(StrictModel):
    tag: str
    label_zh: str


class RequirementAssessment(StrictModel):
    reply: str
    location: str = ""
    target_date: str = ""
    occasions: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    times_of_day: list[str] = Field(default_factory=list)
    climates: list[str] = Field(default_factory=list)
    formalities: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    special_requirements: list[str] = Field(default_factory=list)
    additional_notes: str = ""
    search_brief: str
    missing_fields: list[RequirementField] = Field(default_factory=list)
    updated_fields: list[RequirementField] = Field(default_factory=list)
    tag_translations: list[TagTranslation] = Field(default_factory=list)
    ready_to_plan: bool = False


class RequirementCollector:
    def __init__(self, llm: LLM):
        self.llm = llm

    @staticmethod
    def _implied_formality(messages: list[ChatTurn]) -> str | None:
        """Return only formality entailed by a narrowly defined context phrase."""
        user_text = " ".join(
            message.text for message in messages if message.role == "user"
        ).lower()
        fine_dining_terms = (
            "高級餐廳", "高级餐厅", "高級餐館", "高级餐馆",
            "fine dining", "fine-dining", "luxury restaurant", "upscale restaurant",
        )
        if not any(term in user_text for term in fine_dining_terms):
            return None
        dresses_down = bool(
            re.search(
                r"(?:不要|不想|不用|不必|避免|別|别|不太|不要太).{0,8}(?:正式|隆重)",
                user_text,
            )
            or re.search(
                r"\b(?:not|don't|do not|less)\b.{0,24}\bformal\b|\bcasual\b",
                user_text,
                flags=re.IGNORECASE,
            )
        )
        return "smart casual" if dresses_down else "formal"

    def collect(
        self,
        messages: list[ChatTurn],
        *,
        audience: str | None = None,
        previous_requirements: RequirementSummary | None = None,
    ) -> ClarificationResponse:
        payload = {
            "conversation": [message.model_dump(mode="json") for message in messages],
            "current_context": current_taiwan_context(),
            "audience": audience,
            "previous_requirements": (
                previous_requirements.model_dump(mode="json")
                if previous_requirements
                else None
            ),
        }
        result = self.llm.parse(
            stage="requirement_clarification",
            instructions=REQUIREMENT_COLLECTOR_PROMPT,
            content=[{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
            schema=RequirementAssessment,
        )
        updated_fields = set(result.updated_fields)
        requirement_values = {
            field: (
                getattr(result, field)
                if previous_requirements is None or field in updated_fields
                else getattr(previous_requirements, field)
            )
            for field in REQUIREMENT_VALUE_FIELDS
        }
        implied_formality = self._implied_formality(messages)
        inferred_formality = bool(
            implied_formality and not requirement_values["formalities"]
        )
        if inferred_formality:
            requirement_values["formalities"] = [implied_formality]
        translations = {
            **(
                previous_requirements.tag_translations
                if previous_requirements is not None
                else {}
            ),
            **{item.tag: item.label_zh for item in result.tag_translations},
        }
        if inferred_formality:
            translations[implied_formality] = (
                "正式" if implied_formality == "formal" else "正式休閒"
            )
        missing_fields = list(dict.fromkeys(result.missing_fields))
        if inferred_formality:
            missing_fields = [
                field for field in missing_fields if field != "formalities"
            ]
        search_brief = result.search_brief
        if inferred_formality and implied_formality not in search_brief.lower():
            label = "正式場合" if implied_formality == "formal" else "正式休閒"
            search_brief = f"{search_brief.rstrip('，。 ')}，{label}"
        if inferred_formality:
            formality_label = (
                "正式" if implied_formality == "formal" else "正式休閒"
            )
            reply = (
                f"已了解是高級餐廳用餐，依情境先以{formality_label}處理；"
                "如果想穿得更輕鬆，可以再告訴我。"
                if "正式" in result.reply
                else (
                    f"{result.reply.rstrip()} 已依高級餐廳情境推定為"
                    f"{formality_label}；如果想穿得更輕鬆，可以再告訴我。"
                )
            )
        else:
            reply = result.reply
        defaults = set(previous_requirements.defaulted_fields if previous_requirements else [])
        defaults.difference_update(updated_fields)
        if "location" in updated_fields and "seasons" in defaults:
            requirement_values["seasons"] = []
        if "seasons" in updated_fields and "target_date" in defaults:
            requirement_values["target_date"] = ""
            defaults.discard("target_date")
        summary = with_context_defaults(RequirementSummary(
            **requirement_values,
            search_brief=search_brief,
            tag_translations=translations,
            defaulted_fields=sorted(defaults),
        ))
        missing_fields = [field for field in missing_fields if field not in {"location", "target_date", "seasons", "times_of_day"}]
        if previous_requirements is None and summary.defaulted_fields:
            assumptions = [
                "台灣" if field == "location" else
                summary.target_date if field == "target_date" else
                "、".join(summary.tag_translations.get(tag, tag) for tag in summary.seasons)
                for field in ("location", "target_date", "seasons")
                if field in summary.defaulted_fields
            ]
            reply += f" 時間、季節或地點有其他安排嗎？未補充會先以{'／'.join(assumptions)}搭配，可直接確認。"
        return ClarificationResponse(
            reply=reply,
            requirements=summary,
            missing_fields=missing_fields,
            ready_to_plan=(result.ready_to_plan or (
                not missing_fields and bool(summary.occasions or summary.styles or summary.activities)
            )),
        )


class FashionIntentInterpreter:
    """Interpret user meaning and outfit strategy without writing retrieval queries."""

    name = "fashion-intent-v1"

    def __init__(self, llm: LLM):
        self.llm = llm

    @staticmethod
    def _strategy_text(intent: FashionIntent) -> str:
        values = [
            *intent.core_aesthetic,
            *intent.must_have_visual_cues,
            *intent.optional_visual_cues,
            *intent.styling_principles,
        ]
        for concept in intent.concepts:
            values.extend(
                value
                for value in (
                    concept.concept_name,
                    concept.outfit_formula,
                    concept.upper_role,
                    concept.lower_role,
                    concept.one_piece_role,
                    *concept.visible_cues,
                    *concept.balance_rules,
                )
                if value
            )
        return " ".join(values).lower()

    @classmethod
    def _validate_hard_rule_alignment(
        cls, intent: FashionIntent, hard: UserHardRule | None
    ) -> None:
        if hard is None:
            return
        prohibited: set[str] = set()
        hard_values = [
            *(hard.avoid_colours or []),
            *(hard.avoid_article_types or []),
            *(hard.avoid_master_categories or []),
        ]
        for value in hard_values:
            normalized = value.strip().lower()
            if not normalized:
                continue
            prohibited.add(normalized)
            for aliases in COLOR_ALIASES.values():
                if normalized in {alias.lower() for alias in aliases}:
                    prohibited.update(alias.lower() for alias in aliases)
            for input_aliases, query_aliases in REJECTABLE_CONCEPTS.values():
                all_aliases = {*input_aliases, *query_aliases}
                if normalized in {alias.lower() for alias in all_aliases}:
                    prohibited.update(alias.lower() for alias in all_aliases)

        strategy = cls._strategy_text(intent)
        conflicts = []
        for term in prohibited:
            matched = (
                re.search(rf"\b{re.escape(term)}\b", strategy) is not None
                if term.isascii()
                else term in strategy
            )
            if matched:
                conflicts.append(term)
        if conflicts:
            raise RuntimeError(
                "FashionIntent conflicts with explicit hard rules: "
                + ", ".join(sorted(set(conflicts)))
            )

    def interpret(
        self,
        *,
        raw_user_text: str,
        requirement_summary: RequirementSummary,
        audience: str | None,
        hard: UserHardRule | None,
        style_preferences: list[UserStylePreference] | None,
        refinement: str | None = None,
        previous_intent: FashionIntent | None = None,
        observations: list[OutfitObservation] | None = None,
    ) -> FashionIntent:
        payload = {
            "retrieved_observations": [item.model_dump(mode="json") for item in observations or []],
            "raw_user_text": raw_user_text,
            "requirement_summary": requirement_summary.model_dump(mode="json"),
            "audience": audience,
            "refinement": refinement,
            "previous_fashion_intent": (
                previous_intent.model_dump(mode="json") if previous_intent else None
            ),
            "user_preferences": build_planner_preference_context(
                hard, style_preferences
            ),
        }
        intent = self.llm.parse(
            stage="fashion_intent_interpretation",
            instructions=FASHION_INTENT_INTERPRETER_PROMPT,
            content=[
                {
                    "type": "input_text",
                    "text": json.dumps(payload, ensure_ascii=False),
                }
            ],
            schema=FashionIntent,
        )
        self._validate_hard_rule_alignment(intent, hard)
        return intent


def interpret_fashion_intent_or_none(
    interpreter: FashionIntentInterpreter,
    *,
    enabled: bool,
    raw_user_text: str,
    requirement_summary: RequirementSummary,
    audience: str | None,
    hard: UserHardRule | None,
    style_preferences: list[UserStylePreference] | None,
    refinement: str | None = None,
    previous_intent: FashionIntent | None = None,
    observations: list[OutfitObservation] | None = None,
) -> tuple[FashionIntent | None, bool]:
    """Return a validated intent, falling back without breaking query planning."""
    if not enabled:
        return None, False
    try:
        return (
            interpreter.interpret(
                raw_user_text=raw_user_text,
                requirement_summary=requirement_summary,
                audience=audience,
                hard=hard,
                style_preferences=style_preferences,
                refinement=refinement,
                previous_intent=previous_intent,
                observations=observations,
            ),
            False,
        )
    except (RuntimeError, ValueError) as error:
        logger.warning("Fashion intent fallback used: %s", error)
        return None, True


class RepairedCatalogQuery(StrictModel):
    garment_zone: Literal["upper_body", "lower_body", "one_piece"]
    text: str = Field(min_length=3, max_length=240)


class EnglishQueryRepair(StrictModel):
    queries: list[RepairedCatalogQuery] = Field(min_length=12, max_length=12)


@dataclass(frozen=True)
class PreprocessedQuery:
    """The usable English portion of an LLM query and whether its intent needs repair."""

    text: str | None
    needs_repair: bool


@dataclass(frozen=True)
class NormalizedQueries:
    by_zone: dict[str, list[str]]
    repair_attempted: bool


class QueryOutputNormalizer:
    """Validate and normalize LLM output before it reaches FashionCLIP search."""

    def __init__(self, llm: LLM):
        self.llm = llm

    @staticmethod
    def _preprocess_query(value: str) -> PreprocessedQuery:
        """Clean a candidate search phrase and flag non-English or invalid output."""
        contains_non_ascii = any(ord(character) > 127 for character in value)
        cleaned = re.sub(r"[^\x20-\x7E]+", " ", value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
        cleaned = re.sub(r"\b(?:and|or|but|with)\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" ,;:-")
        is_english_phrase = len(cleaned) >= 3 and re.search(r"[A-Za-z]", cleaned)
        return PreprocessedQuery(
            text=cleaned if is_english_phrase else None,
            needs_repair=contains_non_ascii or not is_english_phrase,
        )

    @staticmethod
    def _allowed_named_colors(
        user_input: str, style_preferences: list[UserStylePreference] | None
    ) -> set[str]:
        sources = [user_input.lower()]
        for row in style_preferences or []:
            if row.is_active:
                sources.append(row.preference_text.lower())
        allowed: set[str] = set()
        for color, aliases in COLOR_ALIASES.items():
            if any(
                (
                    re.search(rf"\b{re.escape(alias.lower())}\b", source) is not None
                    if alias.isascii()
                    else alias.lower() in source
                )
                for alias in aliases
                for source in sources
            ):
                allowed.add(color)
        return allowed

    @staticmethod
    def _remove_unsolicited_colors(value: str, allowed: set[str]) -> str:
        cleaned = value
        for color, aliases in COLOR_ALIASES.items():
            if color in allowed:
                continue
            for alias in sorted(aliases, key=len, reverse=True):
                if alias.isascii():
                    cleaned = re.sub(
                        rf"(?:\b(?:or|and)\s+)?\b{re.escape(alias)}\b(?:\s+(?:or|and)\b)?",
                        " ",
                        cleaned,
                        flags=re.IGNORECASE,
                    )
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s+([,;/])", r"\1", cleaned)
        cleaned = re.sub(r"(?:^|\s)(?:or|and|with)(?=\s*(?:,|$))", " ", cleaned, flags=re.I)
        return cleaned.strip(" ,;:-")

    @staticmethod
    def _remove_contextually_unsuitable_terms(value: str, user_input: str) -> str:
        lowered_input = user_input.lower()
        is_beach = any(term in lowered_input for term in ("海邊", "海边", "beach"))
        denim_requested = any(
            term in lowered_input for term in ("牛仔", "denim", "jean")
        )
        if not is_beach or denim_requested:
            return value
        cleaned = re.sub(r"\b(?:denim|jeans?)\b", " ", value, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", cleaned).strip(" ,;:-")

    @staticmethod
    def _is_rejected(source: str, alias: str) -> bool:
        lowered = source.lower()
        start = 0
        while True:
            index = lowered.find(alias.lower(), start)
            if index < 0:
                return False
            prefix = lowered[max(0, index - 48) : index]
            if CHINESE_REJECTION_PREFIX.search(prefix) or ENGLISH_REJECTION_PREFIX.search(prefix):
                return True
            start = index + len(alias)

    @classmethod
    def _forbidden_query_terms(
        cls,
        user_input: str,
        requirements: RequirementSummary | None,
        hard: UserHardRule | None,
        style_preferences: list[UserStylePreference] | None,
    ) -> set[str]:
        sources = [user_input]
        if requirements is not None:
            sources.extend(requirements.special_requirements)
            sources.append(requirements.additional_notes)
        sources.extend(
            row.preference_text for row in style_preferences or [] if row.is_active
        )
        forbidden: set[str] = set()
        for input_aliases, query_aliases in REJECTABLE_CONCEPTS.values():
            if any(cls._is_rejected(source, alias) for source in sources for alias in input_aliases):
                forbidden.update(query_aliases)

        if hard is not None:
            for value in (*hard.avoid_article_types, *hard.avoid_master_categories):
                normalized = value.strip().lower()
                if normalized:
                    forbidden.add(normalized)
                    if normalized.endswith("s"):
                        forbidden.add(normalized[:-1])
            for avoided_color in hard.avoid_colours:
                normalized = avoided_color.strip().lower()
                for color, aliases in COLOR_ALIASES.items():
                    if normalized == color or normalized in {alias.lower() for alias in aliases}:
                        forbidden.update(alias for alias in aliases if alias.isascii())
        for color, aliases in COLOR_ALIASES.items():
            if any(cls._is_rejected(source, alias) for source in sources for alias in aliases):
                forbidden.update(alias for alias in aliases if alias.isascii())
        return forbidden

    @staticmethod
    def _remove_forbidden_terms(value: str, forbidden: set[str]) -> str:
        cleaned = value
        for term in sorted(forbidden, key=len, reverse=True):
            cleaned = re.sub(rf"\b{re.escape(term)}\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:no|not|without|avoid|excluding)\b", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip(" ,;:-")

    # Check that every garment zone has the required number of candidate directions.
    # Return a dict of the queries by zone if valid, or an empty dict if invalid.
    @staticmethod
    def validate_distribution(
        queries: list[PlannedCatalogQuery],
    ) -> dict[str, list[PlannedCatalogQuery]]:
        by_zone = {zone: [] for zone in QUERY_ZONES}
        for query in queries:
            by_zone[query.garment_zone].append(query)
        counts = {zone: len(items) for zone, items in by_zone.items()}
        if any(counts[zone] != QUERY_COUNTS[zone] for zone in QUERY_ZONES):
            summary = ", ".join(f"{zone}={count}" for zone, count in counts.items())
            raise RuntimeError(
                "Query planner must return upper_body=5, lower_body=5, "
                f"one_piece=2; {summary}"
            )
        return by_zone

    @staticmethod
    def normalized_direction_ids(
        by_zone: dict[str, list[PlannedCatalogQuery]],
    ) -> dict[str, list[str]]:
        upper_ids = [query.direction_id for query in by_zone["upper_body"]]
        lower_ids = [query.direction_id for query in by_zone["lower_body"]]
        if len(set(upper_ids)) == 5 and set(upper_ids) == set(lower_ids):
            separates = {
                "upper_body": upper_ids,
                "lower_body": lower_ids,
            }
        else:
            # Preserve pairing even if the model returns duplicate or mismatched IDs.
            separates = {
                "upper_body": list("ABCDE"),
                "lower_body": list("ABCDE"),
            }
        one_piece_ids = [query.direction_id for query in by_zone["one_piece"]]
        if len(set(one_piece_ids)) != 2:
            one_piece_ids = list("FG")
        return {**separates, "one_piece": one_piece_ids}

    def _repair_invalid_queries(
        self, result: KnowledgeQueryDraft
    ) -> dict[str, list[RepairedCatalogQuery]]:
        """Ask the repair stage for 12 English replacements, or preserve original output."""
        repair_payload = {
            "context_restrictiveness": result.context_restrictiveness,
            "hard_constraints": result.hard_constraints,
            "excluded_query_terms": result.excluded_query_terms,
            "aesthetic_direction": result.aesthetic_direction,
            "queries": [query.model_dump(mode="json") for query in result.queries],
        }
        try:
            repaired = self.llm.parse(
                stage="query_repair",
                instructions=QUERY_REPAIR_SYSTEM_PROMPT,
                content=[
                    {
                        "type": "input_text",
                        "text": json.dumps(repair_payload, ensure_ascii=False),
                    }
                ],
                schema=EnglishQueryRepair,
            )
            return self.validate_distribution(repaired.queries)
        except (RuntimeError, ValueError):
            # A repair failure must not discard usable English from the primary plan.
            return {}

    # Complete repair process
    def normalize_fashion_clip_queries(
        self,
        result: KnowledgeQueryDraft,
        by_zone: dict[str, list[PlannedCatalogQuery]],
        user_input: str,
        style_preferences: list[UserStylePreference] | None,
        requirements: RequirementSummary | None = None,
        hard: UserHardRule | None = None,
    ) -> NormalizedQueries:
        """Repair invalid output, then enforce local safeguards before embedding search."""
        original_by_zone = {
            # preprocess each query (6 total)
            # remove non-English characters, trim whitespace, and flag queries that need repair
            zone: [self._preprocess_query(query.text) for query in by_zone[zone]]
            for zone in QUERY_ZONES
        }
        repair_attempted = any(
            query.needs_repair
            for queries in original_by_zone.values()
            for query in queries
        )
        repaired_by_zone = self._repair_invalid_queries(result) if repair_attempted else {}
        allowed_named_colors = self._allowed_named_colors(user_input, style_preferences)
        forbidden_terms = self._forbidden_query_terms(
            user_input, requirements, hard, style_preferences
        )
        # Never turn an LLM-invented exclusion into a hard filter. Only exclusions
        # verified from the raw request, saved hard rules, or preferences are safe.

        normalized: dict[str, list[str]] = {}
        for zone in QUERY_ZONES:
            normalized[zone] = []
            for index, original in enumerate(original_by_zone[zone]):
                repaired = (
                    self._preprocess_query(repaired_by_zone[zone][index].text).text
                    if zone in repaired_by_zone
                    else None
                )
                query = repaired or original.text or FALLBACK_QUERIES[zone][index]
                query = self._remove_unsolicited_colors(query, allowed_named_colors)
                query = self._remove_contextually_unsuitable_terms(query, user_input)
                query = self._remove_forbidden_terms(query, forbidden_terms)
                fallback = self._remove_forbidden_terms(
                    FALLBACK_QUERIES[zone][index], forbidden_terms
                )
                normalized[zone].append(
                    self._preprocess_query(query).text
                    or self._preprocess_query(fallback).text
                    or f"versatile {zone.replace('_', '-')} garment"
                )
        return NormalizedQueries(normalized, repair_attempted)


class QueryPlanner:
    """Build an LLM query plan, then delegate output safety to QueryOutputNormalizer."""

    name = "catalog-query-agent-v2"

    def __init__(self, llm: LLM):
        self.llm = llm
        self.normalizer = QueryOutputNormalizer(llm)

    @staticmethod
    def _query_warnings(queries: list[QueryDraft]) -> list[str]:
        warnings: list[str] = []
        non_product_phrases = re.compile(
            r"\b(?:for (?:a |the )?(?:date|photos?|wedding|restaurant)|"
            r"taking photos?|makes? (?:you|the wearer) look|not trying too hard)\b",
            flags=re.IGNORECASE,
        )
        garment_terms = {
            "top", "tops", "tee", "tees", "t-shirt", "t-shirts", "shirt",
            "shirts", "blouse", "blouses", "tank", "camisole", "sweater",
            "sweaters", "cardigan", "cardigans", "jacket", "jackets", "blazer",
            "blazers", "vest", "vests", "trousers", "pants", "jeans", "shorts", "skirt", "skirts",
            "dress", "dresses", "jumpsuit", "jumpsuits", "romper", "rompers",
        }
        statement_terms = {
            "graphic", "metallic", "multicolor", "colorful", "printed",
            "embellished", "sequin", "rhinestone", "bold", "statement",
        }
        token_sets: list[tuple[str, set[str]]] = []
        by_direction: dict[str, list[QueryDraft]] = {}
        for query in queries:
            query_label = f"{query.direction_id or query.id}/{query.garment_zone}"
            words = re.findall(r"[a-z]+(?:-[a-z]+)?", query.text.lower())
            tokens = set(words)
            token_sets.append((query_label, tokens))
            if len(words) > 22:
                warnings.append(f"{query_label}: query exceeds 22 English words")
            if non_product_phrases.search(query.text):
                warnings.append(f"{query_label}: query contains non-product context")
            if not tokens.intersection(garment_terms):
                warnings.append(
                    f"{query_label}: query may lack a recognizable garment type"
                )
            if query.direction_id and query.garment_zone in {"upper_body", "lower_body"}:
                by_direction.setdefault(query.direction_id, []).append(query)

        for index, (left_id, left) in enumerate(token_sets):
            for right_id, right in token_sets[index + 1 :]:
                union = left | right
                if union and len(left & right) / len(union) >= 0.8:
                    warnings.append(f"{left_id}/{right_id}: queries are highly similar")
        for direction_id, pair in by_direction.items():
            if len(pair) != 2:
                continue
            statement_counts = [
                len(set(re.findall(r"[a-z]+", query.text.lower())) & statement_terms)
                for query in pair
            ]
            if all(count >= 2 for count in statement_counts):
                warnings.append(
                    f"direction {direction_id}: upper and lower may both be statement pieces"
                )
        return list(dict.fromkeys(warnings))

    @staticmethod
    def _guide_with_intent(
        guide: StylingGuide, intent: FashionIntent | None
    ) -> StylingGuide:
        if intent is None:
            return guide

        def merged(*groups: list[str], limit: int = 12) -> list[str]:
            return list(dict.fromkeys(item for group in groups for item in group))[:limit]

        return guide.model_copy(
            update={
                "concept": intent.user_goal,
                "desired_impression": intent.desired_impression,
                "visual_attributes": merged(
                    intent.must_have_visual_cues,
                    intent.core_aesthetic,
                    guide.visual_attributes,
                ),
                "avoid_misinterpretations": merged(
                    intent.avoid_concepts,
                    guide.avoid_misinterpretations,
                ),
                "styling_principles": merged(
                    intent.styling_principles,
                    guide.styling_principles,
                ),
                "reviewer_checklist": merged(
                    intent.must_have_visual_cues,
                    intent.styling_principles,
                    guide.reviewer_checklist,
                ),
            }
        )

    def plan(
        self,
        user_input: str,
        *,
        requirements: RequirementSummary | None = None,
        audience: str | None = None,
        hard: UserHardRule | None = None,
        style_preferences: list[UserStylePreference] | None = None,
        existing_queries: list[QueryDraft] | None = None,
        refinement: str | None = None,
        fashion_intent: FashionIntent | None = None,
        intent_fallback_used: bool = False,
        include_debug: bool = False,
        observations: list[OutfitObservation] | None = None,
        knowledge_retrieval_note: str = "",
    ) -> PlanResponse:
        # get preference payload for LLM
        preference_payload = build_planner_preference_context(hard, style_preferences)

        # build payload for LLM
        payload = {
            "retrieved_observations": [item.model_dump(mode="json") for item in observations or []],
            "knowledge_retrieval_note": knowledge_retrieval_note,
            "user_request": user_input,
            "outfit_context": (
                requirements.model_dump(mode="json") if requirements else None
            ),
            "audience": audience,
            "refinement": refinement,
            "existing_queries": [
                query.model_dump(mode="json") for query in existing_queries or []
            ],
            "user_preferences": preference_payload,
            "fashion_intent": (
                fashion_intent.model_dump(mode="json") if fashion_intent else None
            ),
        }

        # Call the LLM to generate 12 catalog-retrieval queries.
        result = self.llm.parse(
            stage="query_planning",
            instructions=QUERY_PLANNER_SYSTEM_PROMPT,
            content=[{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
            schema=KnowledgeQueryDraft,
        )

        # Validate
        by_zone = self.normalizer.validate_distribution(result.queries)

        # Normalizer
        normalization_input = " ".join(
            value for value in (user_input, refinement) if value
        )
        normalized_queries = self.normalizer.normalize_fashion_clip_queries(
            result,
            by_zone,
            normalization_input,
            style_preferences,
            requirements,
            hard,
        )
        direction_ids = self.normalizer.normalized_direction_ids(by_zone)

        queries = [
            QueryDraft(
                id=str(uuid4()),
                text=normalized_queries.by_zone[zone][index],
                garment_zone=zone,
                rationale=by_zone[zone][index].rationale,
                direction_id=direction_ids[zone][index],
            )
            for zone in QUERY_ZONES
            for index in range(QUERY_COUNTS[zone])
        ]
        styling_guide = self._guide_with_intent(result.styling_guide, fashion_intent)
        used_ids = list(dict.fromkeys(
            identifier for identifier in result.cited_observation_ids
            if identifier in {item.observation_id for item in observations or []}
        ))
        used_observations = [item for item in observations or [] if item.observation_id in used_ids]
        gaps = result.knowledge_gaps
        if not used_ids and not gaps:
            gaps = [f"缺少能支持此需求的具體搭配依據：{normalization_input}"]
        if knowledge_retrieval_note:
            gaps = [f"待檢索恢復後確認（非確定缺口）：{gap}" for gap in gaps]
        knowledge_note = "；".join(value for value in (knowledge_retrieval_note, result.knowledge_note) if value)
        if gaps:
            logger.warning("planning_knowledge_gap %s", json.dumps({
                "request": normalization_input,
                "audience": audience,
                "gaps": gaps,
                "retrieval_error": knowledge_retrieval_note,
                "retrieved_ids": [item.observation_id for item in observations or []],
                "used_ids": used_ids,
            }, ensure_ascii=False))
        # The model may interleave directions (A upper, A lower, B upper, ...),
        # while our public query contract groups rows by garment zone. Compare
        # corresponding rows inside each zone instead of zipping the two global
        # lists, otherwise unchanged queries are incorrectly reported as edits.
        final_by_zone = {
            zone: [query for query in queries if query.garment_zone == zone]
            for zone in QUERY_ZONES
        }
        normalizer_changes = [
            {
                "direction_id": after.direction_id,
                "garment_zone": zone,
                "before": before.text,
                "after": after.text,
            }
            for zone in QUERY_ZONES
            for before, after in zip(by_zone[zone], final_by_zone[zone], strict=True)
            if before.text != after.text
        ]
        trace_payload = {
            "knowledge_observations": [item.model_dump(mode="json") for item in observations or []],
            "knowledge_used_ids": used_ids,
            "knowledge_gaps": gaps,
            "knowledge_note": knowledge_note,
            "raw_user_text": user_input,
            "requirement_summary": (
                requirements.model_dump(mode="json") if requirements else None
            ),
            "fashion_intent": (
                fashion_intent.model_dump(mode="json") if fashion_intent else None
            ),
            "generated_queries_before_normalization": [
                query.model_dump(mode="json") for query in result.queries
            ],
            "generated_queries_after_normalization": [
                query.model_dump(mode="json") for query in queries
            ],
            "normalizer_changes": normalizer_changes,
            "query_warnings": self._query_warnings(queries),
            "intent_fallback_used": intent_fallback_used,
            "model": settings.query_planner_model,
            "prompt_version": "intent-v1" if fashion_intent else "legacy-v2",
        }
        logger.info(
            "query_plan_trace %s",
            json.dumps(trace_payload, ensure_ascii=False),
        )

        return PlanResponse(
            original_input=user_input,
            queries=queries,
            planner=self.name,
            audience=audience,
            knowledge_observation_ids=used_ids,
            knowledge_observations=used_observations,
            knowledge_gaps=gaps,
            knowledge_note=knowledge_note,
            planning_note=(
                f"{result.planning_note} FashionCLIP 搜尋句已自動正規化為英文。"
                if normalized_queries.repair_attempted
                else result.planning_note
            ),
            styling_guide=styling_guide,
            fashion_intent=fashion_intent,
            debug=(QueryPlanDebug.model_validate(trace_payload) if include_debug else None),
        )
