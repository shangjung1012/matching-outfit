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
    if requirements.location:
        lines.append(f"location: {requirements.location}")
    if requirements.target_date:
        lines.append(f"target date: {requirements.target_date}")
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
            # Per single catalog item, not a total-outfit budget (see outfit_budget_max).
            "item_price_min": hard.price_min,
            "item_price_max": hard.price_max,
        }

    for row in style_preferences or []:
        if not row.is_active:
            continue
        payload.setdefault("outfit_memories", []).append(
            {
                "preference_sentence": row.preference_text,
                "preference_type": row.preference_type,
                **{
                    field: getattr(row, field) or []
                    for field in OUTFIT_CONTEXT_FIELDS
                },
            }
        )
    return payload
