"""Preference payloads shared by LLM-backed recommendation stages."""

from app.models.user_preference import UserHardRule, UserStylePreference


def relevant_style_preferences(
    rows: list[UserStylePreference], user_context: str
) -> list[UserStylePreference]:
    """Return preference sentences whose saved context matches this request."""
    normalized_context = user_context.strip().lower()
    selected: list[UserStylePreference] = []
    for row in rows:
        scopes = [
            *(row.context_occasions or []),
            *(row.context_times or []),
            *(row.context_situations or []),
        ]
        if not scopes or any(
            scope.strip().lower() in normalized_context
            or normalized_context in scope.strip().lower()
            for scope in scopes
            if scope.strip()
        ):
            selected.append(row)
    return selected


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

    for row in style_preferences or []:
        if not row.is_active:
            continue
        payload.setdefault("outfit_memories", []).append(
            {
                "preference_sentence": row.preference_text,
                "occasions": row.context_occasions or [],
                "times_or_seasons": row.context_times or [],
                "contexts": row.context_situations or [],
            }
        )
    return payload
