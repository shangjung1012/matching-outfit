from datetime import datetime, timezone

from app.schemas.workflow import ChatTurn, RequirementSummary, SessionHardRules
from app.services.requirement_context import current_taiwan_context, with_context_defaults
from app.services.query_planner import RequirementAssessment, RequirementCollector

NOW = datetime(2026, 9, 17, 17, 0, tzinfo=timezone.utc)


def test_current_date_uses_taiwan_timezone_across_midnight():
    assert current_taiwan_context(NOW)["today"] == "2026-09-18"
    summary = with_context_defaults(None, now=NOW)
    assert summary.location == "台灣"
    assert summary.target_date == "2026-09-18"
    assert summary.seasons == ["autumn"]
    assert summary.times_of_day == []
    assert summary.climates == []
    assert set(summary.defaulted_fields) == {"location", "target_date", "seasons"}


def test_explicit_season_does_not_get_conflicting_current_date():
    summary = with_context_defaults(RequirementSummary(seasons=["winter"]), now=NOW)
    assert summary.seasons == ["winter"]
    assert summary.target_date == ""
    assert summary.defaulted_fields == ["location"]


def test_explicit_future_date_drives_taiwan_season():
    summary = with_context_defaults(RequirementSummary(target_date="2026-12-25"), now=NOW)
    assert summary.target_date == "2026-12-25"
    assert summary.seasons == ["winter"]
    assert "target_date" not in summary.defaulted_fields


def test_foreign_location_does_not_get_taiwan_calendar_season():
    summary = with_context_defaults(RequirementSummary(location="澳洲"), now=NOW)
    assert summary.location == "澳洲"
    assert summary.seasons == []


class StubLLM:
    def __init__(self, **fields):
        self.fields = fields

    def parse(self, **_):
        return RequirementAssessment(reply="已了解需求。", search_brief="拍照穿搭", **self.fields)


def test_optional_context_question_is_only_added_on_first_turn():
    collector = RequirementCollector(StubLLM())
    first = collector.collect([ChatTurn(role="user", text="幫我搭拍照穿搭")])
    assert "其他安排嗎" in first.reply
    second = collector.collect(
        [ChatTurn(role="user", text="沒特別要求")], previous_requirements=first.requirements
    )
    assert "其他安排嗎" not in second.reply
    assert second.requirements.target_date == first.requirements.target_date


def test_explicit_season_overrides_previous_defaults():
    previous = with_context_defaults(None, now=NOW)
    result = RequirementCollector(StubLLM(seasons=["winter"], updated_fields=["seasons"])).collect(
        [ChatTurn(role="user", text="改成冬天")], previous_requirements=previous
    )
    assert result.requirements.seasons == ["winter"]
    assert result.requirements.target_date == ""
    assert "seasons" not in result.requirements.defaulted_fields


def test_clarification_preserves_initialized_hard_rules_and_budget():
    previous = RequirementSummary(
        hard_rules=SessionHardRules(price_max=1800),
        outfit_budget_max=5400,
    )
    result = RequirementCollector(
        StubLLM(outfit_budget_max=4000, updated_fields=["outfit_budget_max"])
    ).collect(
        [ChatTurn(role="user", text="整套預算改成 4000 元")],
        previous_requirements=previous,
    )

    assert result.requirements.hard_rules == previous.hard_rules
    assert result.requirements.outfit_budget_max == 4000


def test_explicit_date_recalculates_default_season():
    previous = with_context_defaults(None, now=NOW)
    result = RequirementCollector(StubLLM(target_date="2026-12-25", updated_fields=["target_date"])).collect(
        [ChatTurn(role="user", text="聖誕節穿")], previous_requirements=previous
    )
    assert result.requirements.seasons == ["winter"]
    assert "target_date" not in result.requirements.defaulted_fields


def test_foreign_location_override_clears_taiwan_default_season():
    previous = with_context_defaults(None, now=NOW)
    result = RequirementCollector(StubLLM(location="澳洲", updated_fields=["location"])).collect(
        [ChatTurn(role="user", text="地點改成澳洲")], previous_requirements=previous
    )
    assert result.requirements.seasons == []


def test_optional_context_does_not_block_readiness():
    result = RequirementCollector(StubLLM(
        occasions=["dining"], missing_fields=["seasons", "location", "target_date"],
    )).collect([ChatTurn(role="user", text="去吃飯")])
    assert result.missing_fields == []
    assert result.ready_to_plan is True


def test_unspecified_budget_defaults_to_full_outfit_budget():
    result = RequirementCollector(StubLLM()).collect(
        [ChatTurn(role="user", text="上班簡約風，預算 3000 元")]
    )

    assert result.requirements.outfit_budget_max == 3000
