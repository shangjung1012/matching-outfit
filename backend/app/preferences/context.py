"""Preference payloads shared by LLM-backed recommendation stages."""

from app.models.user_preference import UserHardRule, UserStylePreference
from app.schemas.workflow import RequirementSummary


OUTFIT_CONTEXT_FIELDS = (
    "occasions",
    "seasons",
    "times_of_day",
    "climates",
    "formalities",
    "activities",
    "styles",
)


def outfit_context_embedding_text(
    requirements: RequirementSummary | None, fallback: str = ""
) -> str:
    """Serialize user context using the same labels as fashion observations."""
    if requirements is None:
        return fallback.strip()
    lines = [
        f"{field.replace('_', ' ')}: {', '.join(getattr(requirements, field))}"
        for field in OUTFIT_CONTEXT_FIELDS
        if getattr(requirements, field)
    ]
    if requirements.special_requirements:
        lines.append(
            f"special requirements: {', '.join(requirements.special_requirements)}"
        )
    if requirements.additional_notes:
        lines.append(f"additional notes: {requirements.additional_notes}")
    return "\n".join(lines) or fallback.strip()


def build_planner_preference_context(
    hard: UserHardRule | None,
    style_preferences: list[UserStylePreference] | None,
) -> dict:
    """Serialize persisted preferences into the query planner's LLM context."""
    payload: dict = {}
    if hard is not None:
        payload["user_profile"] = {
            "gender": hard.gender,
            "age": hard.age,
            "height_cm": hard.height_cm,
            "weight_kg": hard.weight_kg,
        }
        payload["hard_rules"] = {
            "avoid_colours": hard.avoid_colours or [],
            "avoid_article_types": hard.avoid_article_types or [],
            "avoid_master_categories": hard.avoid_master_categories or [],
            "price_min": hard.price_min,
            "price_max": hard.price_max,
            "notes": hard.notes,
        }

    for row in style_preferences or []:
        if not row.is_active:
            continue
        payload.setdefault("outfit_memories", []).append(
            {
                "preference_sentence": row.preference_text,
                **{
                    field: getattr(row, field) or []
                    for field in OUTFIT_CONTEXT_FIELDS
                },
            }
        )
    return payload
