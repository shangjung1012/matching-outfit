import re
from uuid import uuid4

from app.models.user_preference import UserPreference
from app.schemas import PlanResponse, QueryDraft

COLOR_TERMS = {
    "黑": "black",
    "白": "white",
    "藍": "blue",
    "紅": "red",
    "綠": "green",
    "灰": "gray",
    "粉": "pink",
    "米": "beige",
    "black": "black",
    "white": "white",
    "blue": "blue",
    "red": "red",
    "green": "green",
}
STYLE_TERMS = {
    "正式": "formal",
    "休閒": "casual",
    "簡約": "minimal",
    "運動": "sporty",
    "復古": "retro",
    "街頭": "streetwear",
    "約會": "date-night",
    "上班": "office",
    "婚禮": "wedding guest",
    "formal": "formal",
    "casual": "casual",
    "minimal": "minimal",
    "sporty": "sporty",
    "retro": "retro",
    "streetwear": "streetwear",
    "office": "office",
}


class QueryPlanner:
    """Deterministic planner with the same contract as a future LLM-backed agent."""

    name = "rule-based-scaffold-v1"

    def plan(
        self,
        user_input: str,
        preference: UserPreference | None = None,
        refinement: str | None = None,
        zones: list[str] | None = None,
    ) -> PlanResponse:
        combined = " ".join(part for part in (user_input, refinement) if part)
        colors = self._matches(combined, COLOR_TERMS)
        styles = self._matches(combined, STYLE_TERMS)
        if preference:
            colors.extend(preference.favorite_colors or [])
            styles.extend(preference.preferred_styles or [])

        details = " ".join(dict.fromkeys([*colors, *styles])) or "versatile casual"
        budget = self._budget_text(combined, preference)
        suffix = f", {budget}" if budget else ""
        lower_item = "trousers" if any(term in combined.lower() for term in ("不要裙", "no skirt")) else "trousers or skirt"
        query_specs = [
            ("upper_body", f"{details} upper-body top{suffix}"),
            ("lower_body", f"{details} {lower_item}{suffix}"),
            ("one_piece", f"{details} one-piece dress or jumpsuit{suffix}"),
        ]
        if zones:
            query_specs = [spec for spec in query_specs if spec[0] in zones]
        queries = [
            QueryDraft(
                id=str(uuid4()),
                text=text,
                garment_zone=zone,
                rationale=f"Search the {zone.replace('_', ' ')} candidate pool.",
            )
            for zone, text in query_specs
        ]
        return PlanResponse(original_input=combined, queries=queries, planner=self.name)

    @staticmethod
    def _matches(text: str, mapping: dict[str, str]) -> list[str]:
        lowered = text.lower()
        return [value for key, value in mapping.items() if key in lowered]

    @staticmethod
    def _budget_text(text: str, preference: UserPreference | None) -> str:
        numbers = [int(value) for value in re.findall(r"\d+", text.replace(",", ""))]
        if numbers:
            return f"budget under {max(numbers)} TWD"
        if preference and preference.preferred_price_max:
            return f"budget under {preference.preferred_price_max} TWD"
        return ""


query_planner = QueryPlanner()
