import json
import re
from typing import Literal
from uuid import uuid4

from pydantic import Field

from app.models.user_preference import UserPreference
from app.schemas.styling import OutfitObservation, StrictModel
from app.schemas.workflow import PlanResponse, QueryDraft
from app.services.structured_llm import StructuredLLM


QUERY_PLANNER_SYSTEM_PROMPT = """
You are the query-planning stage of a practical outfit recommendation system.
Transform the user's request into exactly six concise English FashionCLIP queries:
two upper_body queries, two lower_body queries, and two one_piece queries.
The two queries within each garment zone must describe meaningfully different but
equally suitable visual directions. This broadens catalog recall when an exact item is
unavailable and prevents an over-specific phrase from producing near-identical items.

First decide how restrictive the occasion is. Gala dinners, weddings, funerals,
interviews, explicit dress codes, and safety requirements create hard constraints.
Shopping, cafes, sightseeing, and ordinary leisure usually impose few constraints;
for those requests prioritize visual coherence and the user's taste. Do not invent a
prohibition merely because a place was mentioned.

Infer practical constraints from the physical environment, including temperature,
humidity, sun, water, sand, terrain, and required movement. Prefer materials and
silhouettes that remain comfortable there; for example, avoid heavy, rigid, or
slow-drying garments in hot, wet, or sandy settings unless the user requests them.
For a beach request, assume possible heat, water, and sand exposure: do not choose
denim bottoms unless the user explicitly asks for denim.

Each FashionCLIP query must contain only positive, visually observable attributes:
garment type, color family, pattern, silhouette, material appearance, formality, and
style. Do not include prices, explanations, negations, abstract occasion names alone,
or demographic labels. The upper and lower queries must be compatible with each other.
The one-piece query must be a complete alternative outfit direction.

Never introduce a specific named color unless the user explicitly requested that color
or it is present in the user's saved color preferences. Retrieved observations must not
override this rule. When color character matters but no color was requested, use broad
visual properties such as bright color, muted tone, dark tone, light tone, neutral tone,
or colorful instead of names such as white, blue, beige, or black.

Retrieved observations are evidence, not absolute truth. Use only relevant observations
and cite only supplied observation IDs. Respect the requested audience and preferences.
Perform a final self-check that all three zones occur exactly twice, the queries are
visually searchable, varied, and the upper/lower directions can form coherent outfits. Write rationales and
the planning note in concise Traditional Chinese.
""".strip()

QUERY_REPAIR_SYSTEM_PROMPT = """
You repair FashionCLIP catalog queries. Rewrite all three supplied query texts as
concise ASCII English phrases while preserving their garment zone and visual intent.
Use only positive, visually observable clothing attributes. Return exactly six queries,
with upper_body, lower_body, and one_piece each occurring twice. Keep the two query
directions within each zone meaningfully different. Do not translate rationales or
add explanations.
""".strip()

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


class KnowledgeQueryDraft(StrictModel):
    context_restrictiveness: Literal["low", "medium", "high"]
    hard_constraints: list[str] = Field(default_factory=list)
    aesthetic_direction: list[str] = Field(default_factory=list)
    queries: list[PlannedCatalogQuery] = Field(min_length=6, max_length=6)
    cited_observation_ids: list[str] = Field(default_factory=list)
    planning_note: str


class RepairedCatalogQuery(StrictModel):
    garment_zone: Literal["upper_body", "lower_body", "one_piece"]
    text: str = Field(min_length=3, max_length=240)


class EnglishQueryRepair(StrictModel):
    queries: list[RepairedCatalogQuery] = Field(min_length=6, max_length=6)


class KnowledgeQueryPlanner:
    name = "knowledge-agent-v1"

    def __init__(self, llm: StructuredLLM, model: str):
        self.llm = llm
        self.model = model

    @staticmethod
    def _english_query(value: str) -> str | None:
        cleaned = re.sub(r"[^\x20-\x7E]+", " ", value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
        cleaned = re.sub(r"\b(?:and|or|but|with)\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" ,;:-")
        if len(cleaned) < 3 or not re.search(r"[A-Za-z]", cleaned):
            return None
        return cleaned

    @staticmethod
    def _contains_non_ascii(value: str) -> bool:
        return any(ord(character) > 127 for character in value)

    @staticmethod
    def _allowed_named_colors(
        user_input: str, preference: UserPreference | None
    ) -> set[str]:
        sources = [user_input.lower()]
        if preference is not None:
            sources.extend(value.lower() for value in preference.favorite_colors or [])
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

    def _normalized_queries(
        self,
        result: KnowledgeQueryDraft,
        by_zone: dict[str, list[PlannedCatalogQuery]],
        allowed_named_colors: set[str],
        user_input: str,
    ) -> tuple[dict[str, list[str]], bool]:
        expected_zones = ("upper_body", "lower_body", "one_piece")
        needs_repair = any(
            self._contains_non_ascii(query.text)
            or self._english_query(query.text) is None
            for zone in expected_zones
            for query in by_zone[zone]
        )
        repaired_by_zone: dict[str, list[RepairedCatalogQuery]] = {}
        repair_attempted = False
        if needs_repair:
            repair_attempted = True
            repair_payload = {
                "context_restrictiveness": result.context_restrictiveness,
                "hard_constraints": result.hard_constraints,
                "aesthetic_direction": result.aesthetic_direction,
                "queries": [query.model_dump(mode="json") for query in result.queries],
            }
            try:
                repaired = self.llm.parse(
                    model=self.model,
                    instructions=QUERY_REPAIR_SYSTEM_PROMPT,
                    content=[
                        {
                            "type": "input_text",
                            "text": json.dumps(repair_payload, ensure_ascii=False),
                        }
                    ],
                    schema=EnglishQueryRepair,
                )
                candidate_by_zone = {zone: [] for zone in expected_zones}
                for query in repaired.queries:
                    candidate_by_zone[query.garment_zone].append(query)
                if all(len(candidate_by_zone[zone]) == 2 for zone in expected_zones):
                    repaired_by_zone = candidate_by_zone
            except (RuntimeError, ValueError):
                # A translation failure must not discard the valid knowledge plan.
                repaired_by_zone = {}

        normalized: dict[str, list[str]] = {}
        for zone in expected_zones:
            normalized[zone] = []
            for index, original_query in enumerate(by_zone[zone]):
                original = self._english_query(original_query.text)
                repaired = (
                    self._english_query(repaired_by_zone[zone][index].text)
                    if zone in repaired_by_zone
                    else None
                )
                query = repaired or original or FALLBACK_QUERIES[zone][index]
                query = self._remove_unsolicited_colors(query, allowed_named_colors)
                query = self._remove_contextually_unsuitable_terms(query, user_input)
                normalized[zone].append(
                    self._english_query(query) or FALLBACK_QUERIES[zone][index]
                )
        return normalized, repair_attempted

    def plan(
        self,
        user_input: str,
        observations: list[OutfitObservation],
        *,
        audience: str | None = None,
        preference: UserPreference | None = None,
        existing_queries: list[QueryDraft] | None = None,
        refinement: str | None = None,
    ) -> PlanResponse:
        preference_payload = {}
        if preference is not None:
            preference_payload = {
                "favorite_colors": preference.favorite_colors or [],
                "disliked_colors": preference.disliked_colors or [],
                "preferred_styles": preference.preferred_styles or [],
                "preferred_usages": preference.preferred_usages or [],
                "favorite_article_types": preference.favorite_article_types or [],
                "disliked_article_types": preference.disliked_article_types or [],
                "preferred_price_min": preference.preferred_price_min,
                "preferred_price_max": preference.preferred_price_max,
                "notes": preference.notes,
            }
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
        result = self.llm.parse(
            model=self.model,
            instructions=QUERY_PLANNER_SYSTEM_PROMPT,
            content=[{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
            schema=KnowledgeQueryDraft,
        )
        expected_zones = ("upper_body", "lower_body", "one_piece")
        by_zone = {zone: [] for zone in expected_zones}
        for query in result.queries:
            by_zone[query.garment_zone].append(query)
        if not all(len(by_zone[zone]) == 2 for zone in expected_zones):
            raise RuntimeError("Query planner did not return exactly two queries for each garment zone")
        normalized_queries, repair_attempted = self._normalized_queries(
            result,
            by_zone,
            self._allowed_named_colors(user_input, preference),
            user_input,
        )
        available_ids = {observation.observation_id for observation in observations}
        cited_ids = [
            identifier for identifier in result.cited_observation_ids if identifier in available_ids
        ]
        return PlanResponse(
            original_input=user_input,
            queries=[
                QueryDraft(
                    id=str(uuid4()),
                    text=normalized_queries[zone][index],
                    garment_zone=zone,
                    rationale=by_zone[zone][index].rationale,
                )
                for zone in expected_zones
                for index in range(2)
            ],
            planner=self.name,
            audience=audience,
            knowledge_observation_ids=cited_ids,
            planning_note=(
                f"{result.planning_note} FashionCLIP 搜尋句已自動正規化為英文。"
                if repair_attempted
                else result.planning_note
            ),
        )
