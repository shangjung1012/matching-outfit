"""Preference payloads shared by LLM-backed recommendation stages."""

from app.models.user_preference import UserHardRule, UserStylePreference


def build_planner_preference_context(
    hard: UserHardRule | None,
    style_preferences: list[UserStylePreference] | None,
) -> dict:
    """Serialize persisted preferences into the query planner's LLM context."""
    payload: dict = {}
    if hard is not None:
        payload["hard_rules"] = {
            "avoid_colours": hard.avoid_colours or [],
            "avoid_article_types": hard.avoid_article_types or [],
            "avoid_master_categories": hard.avoid_master_categories or [],
            "price_min": hard.price_min,
            "price_max": hard.price_max,
            "notes": hard.notes,
        }

    prefer: list[dict] = []
    avoid: list[dict] = []
    for row in style_preferences or []:
        if not row.is_active:
            continue
        entry = {"axis": row.axis, "value": row.value, "zone": row.zone}
        (prefer if row.polarity == "prefer" else avoid).append(entry)
    if prefer:
        payload["soft_prefer"] = prefer
    if avoid:
        payload["soft_avoid"] = avoid
    return payload
