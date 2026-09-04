"""Runtime date/location assumptions shared by the recommendation stages."""

from datetime import date, datetime, timedelta, timezone

from app.schemas.workflow import RequirementSummary

TAIPEI_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Taipei")
SEASON_LABELS = {"spring": "春季", "summer": "夏季", "autumn": "秋季", "winter": "冬季"}


def current_taiwan_context(now: datetime | None = None) -> dict[str, str]:
    current = (now or datetime.now(timezone.utc)).astimezone(TAIPEI_TIMEZONE)
    return {
        "local_now": current.isoformat(timespec="seconds"),
        "today": current.date().isoformat(),
        "timezone": "Asia/Taipei",
        "default_location": "台灣",
    }


def with_context_defaults(
    requirements: RequirementSummary | None, *, now: datetime | None = None
) -> RequirementSummary:
    summary = (requirements or RequirementSummary()).model_copy(deep=True)
    defaults = set(summary.defaulted_fields)
    if not summary.location.strip():
        summary.location = "台灣"
        defaults.add("location")
    if summary.location.strip().lower() not in {"台灣", "臺灣", "taiwan"} and "seasons" in defaults:
        summary.seasons = []
        defaults.discard("seasons")
    # An explicitly requested season is enough temporal information. Do not
    # attach today's date to e.g. a winter outfit requested during summer.
    if not summary.target_date and not summary.seasons:
        summary.target_date = current_taiwan_context(now)["today"]
        defaults.add("target_date")
    if summary.target_date and summary.location.strip().lower() in {"台灣", "臺灣", "taiwan"}:
        if not summary.seasons or "seasons" in defaults:
            try:
                month = date.fromisoformat(summary.target_date).month
            except ValueError:
                pass
            else:
                season = ("winter", "spring", "summer", "autumn")[(month % 12) // 3]
                summary.seasons = [season]
                summary.tag_translations[season] = SEASON_LABELS[season]
                defaults.add("seasons")
    summary.defaulted_fields = sorted(defaults)
    return summary
