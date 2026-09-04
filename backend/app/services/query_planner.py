import json
import re
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4
from pathlib import Path

from pydantic import Field

from app.models.user_preference import UserHardRule, UserStylePreference
from app.schemas.fashion_knowledge import OutfitObservation, StrictModel
from app.schemas.workflow import (
    ChatTurn,
    ClarificationResponse,
    PlanResponse,
    QueryDraft,
    ReferenceLink,
    RequirementSummary,
)
from app.services.integration_tools.llm import LLM
from app.preferences.context import build_planner_preference_context

# get system and general prompts for QueryPlanner
PROMPTS_DIR = Path(__file__).parent / "prompts"
QUERY_PLANNER_SYSTEM_PROMPT = (PROMPTS_DIR / "QueryPlanner.txt").read_text(encoding="utf-8").strip()
QUERY_REPAIR_SYSTEM_PROMPT = (PROMPTS_DIR / "QueryPlannerSys.txt").read_text(encoding="utf-8").strip()
REQUIREMENT_COLLECTOR_PROMPT = (PROMPTS_DIR / "RequirementCollector.txt").read_text(
    encoding="utf-8"
).strip()
QUERY_ZONES = ("upper_body", "lower_body", "one_piece")

FALLBACK_QUERIES = {
    "upper_body": (
        "visually coherent versatile relaxed upper-body top",
        "visually coherent versatile structured upper-body top",
    ),
    "lower_body": (
        "visually coherent versatile relaxed lower-body trousers or skirt",
        "visually coherent versatile tailored lower-body trousers or skirt",
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


class PlannedCatalogQuery(StrictModel):
    garment_zone: Literal["upper_body", "lower_body", "one_piece"]
    text: str = Field(min_length=3, max_length=240)
    rationale: str = Field(min_length=2, max_length=300)
    cited_observation_ids: list[str] = Field(default_factory=list)


class KnowledgeQueryDraft(StrictModel):
    context_restrictiveness: Literal["low", "medium", "high"]
    hard_constraints: list[str] = Field(default_factory=list)
    aesthetic_direction: list[str] = Field(default_factory=list)
    queries: list[PlannedCatalogQuery] = Field(min_length=6, max_length=6)
    cited_observation_ids: list[str] = Field(default_factory=list)
    planning_note: str


class RequirementAssessment(StrictModel):
    reply: str
    occasion: str = ""
    time: str = ""
    context: str = ""
    special_requirements: str = ""
    additional_notes: str = ""
    search_brief: str
    missing_fields: list[
        Literal[
            "occasion", "time", "context", "special_requirements", "additional_notes"
        ]
    ] = Field(default_factory=list)
    ready_to_plan: bool = False


class RequirementCollector:
    def __init__(self, llm: LLM):
        self.llm = llm

    def collect(
        self,
        messages: list[ChatTurn],
        *,
        audience: str | None = None,
        hard: UserHardRule | None = None,
        style_preferences: list[UserStylePreference] | None = None,
    ) -> ClarificationResponse:
        payload = {
            "conversation": [message.model_dump(mode="json") for message in messages],
            "audience": audience,
            "user_preferences": build_planner_preference_context(hard, style_preferences),
        }
        result = self.llm.parse(
            stage="requirement_clarification",
            instructions=REQUIREMENT_COLLECTOR_PROMPT,
            content=[{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
            schema=RequirementAssessment,
        )
        return ClarificationResponse(
            reply=result.reply,
            requirements=RequirementSummary(
                occasion=result.occasion,
                time=result.time,
                context=result.context,
                special_requirements=result.special_requirements,
                additional_notes=result.additional_notes,
                search_brief=result.search_brief,
            ),
            missing_fields=list(dict.fromkeys(result.missing_fields)),
            ready_to_plan=result.ready_to_plan,
        )


class RepairedCatalogQuery(StrictModel):
    garment_zone: Literal["upper_body", "lower_body", "one_piece"]
    text: str = Field(min_length=3, max_length=240)


class EnglishQueryRepair(StrictModel):
    queries: list[RepairedCatalogQuery] = Field(min_length=6, max_length=6)


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

    # Check if exactly two candidate directions are present in each garment zone, raising an error if not.
    # Return a dict of the queries by zone if valid, or an empty dict if invalid.
    @staticmethod
    def validate_distribution(
        queries: list[PlannedCatalogQuery],
    ) -> dict[str, list[PlannedCatalogQuery]]:
        by_zone = {zone: [] for zone in QUERY_ZONES}
        for query in queries:
            by_zone[query.garment_zone].append(query)
        counts = {zone: len(items) for zone, items in by_zone.items()}
        if any(count != 2 for count in counts.values()):
            summary = ", ".join(f"{zone}={count}" for zone, count in counts.items())
            raise RuntimeError(f"Query planner must return two queries per zone; {summary}")
        return by_zone

    def _repair_invalid_queries(
        self, result: KnowledgeQueryDraft
    ) -> dict[str, list[RepairedCatalogQuery]]:
        """Ask the repair stage for six English replacements, or preserve original output."""
        repair_payload = {
            "context_restrictiveness": result.context_restrictiveness,
            "hard_constraints": result.hard_constraints,
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
                normalized[zone].append(
                    self._preprocess_query(query).text or FALLBACK_QUERIES[zone][index]
                )
        return NormalizedQueries(normalized, repair_attempted)


class QueryPlanner:
    """Build an LLM query plan, then delegate output safety to QueryOutputNormalizer."""

    name = "knowledge-agent-v1"

    def __init__(self, llm: LLM):
        self.llm = llm
        self.normalizer = QueryOutputNormalizer(llm)

    def plan(
        self,
        user_input: str,
        observations: list[OutfitObservation],
        *,
        audience: str | None = None,
        hard: UserHardRule | None = None,
        style_preferences: list[UserStylePreference] | None = None,
        existing_queries: list[QueryDraft] | None = None,
        refinement: str | None = None,
    ) -> PlanResponse:
        # get preference payload for LLM
        preference_payload = build_planner_preference_context(hard, style_preferences)

        # build payload for LLM
        payload = {
            "user_request": user_input,
            "audience": audience,
            "refinement": refinement,
            "existing_queries": [
                query.model_dump(mode="json") for query in existing_queries or []
            ],
            "user_preferences": preference_payload,
            "retrieved_observations": [
                observation.model_dump(mode="json") for observation in observations
            ],
        }

        # Call the LLM to generate 6 queries
        result = self.llm.parse(
            stage="query_planning",
            instructions=QUERY_PLANNER_SYSTEM_PROMPT,
            content=[{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
            schema=KnowledgeQueryDraft,
        )

        # Validate
        by_zone = self.normalizer.validate_distribution(result.queries)

        # Normalizer
        normalized_queries = self.normalizer.normalize_fashion_clip_queries(
            result,
            by_zone,
            user_input,
            style_preferences,
        )

        observations_by_id = {
            observation.observation_id: observation for observation in observations
        }

        def query_citations(
            query: PlannedCatalogQuery,
        ) -> tuple[list[str], list[ReferenceLink]]:
            identifiers = list(
                dict.fromkeys(
                    identifier
                    for identifier in query.cited_observation_ids
                    if identifier in observations_by_id
                )
            )
            references_by_url: dict[str, ReferenceLink] = {}
            for identifier in identifiers:
                observation = observations_by_id[identifier]
                if not observation.source_url:
                    continue
                references_by_url.setdefault(
                    observation.source_url,
                    ReferenceLink(
                        title=(
                            observation.source_title
                            or observation.source_name
                            or observation.source_url
                        ),
                        url=observation.source_url,
                    ),
                )
            return identifiers, list(references_by_url.values())

        query_citation_map = {
            (zone, index): query_citations(by_zone[zone][index])
            for zone in QUERY_ZONES
            for index in range(2)
        }
        cited_ids = list(
            dict.fromkeys(
                [
                    identifier
                    for identifier in result.cited_observation_ids
                    if identifier in observations_by_id
                ]
                + [
                    identifier
                    for identifiers, _ in query_citation_map.values()
                    for identifier in identifiers
                ]
            )
        )
        return PlanResponse(
            original_input=user_input,
            queries=[
                QueryDraft(
                    id=str(uuid4()),
                    text=normalized_queries.by_zone[zone][index],
                    garment_zone=zone,
                    rationale=by_zone[zone][index].rationale,
                    knowledge_observation_ids=query_citation_map[(zone, index)][0],
                    references=query_citation_map[(zone, index)][1],
                )
                for zone in QUERY_ZONES
                for index in range(2)
            ],
            planner=self.name,
            audience=audience,
            knowledge_observation_ids=cited_ids,
            planning_note=(
                f"{result.planning_note} FashionCLIP 搜尋句已自動正規化為英文。"
                if normalized_queries.repair_attempted
                else result.planning_note
            ),
        )
