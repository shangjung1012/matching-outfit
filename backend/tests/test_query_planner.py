import json
from collections import Counter

from app.models.user_preference import UserHardRule, UserStylePreference
from app.preferences.context import build_planner_preference_context
from app.schemas import ChatTurn
from app.services.query_planner import (
    EnglishQueryRepair,
    KnowledgeQueryDraft,
    PlannedCatalogQuery,
    QueryOutputNormalizer,
    QueryPlanner,
    RepairedCatalogQuery,
    RequirementAssessment,
    RequirementCollector,
)


class FakeRequirementLLM:
    def __init__(self):
        self.payload = None

    def parse(self, *, schema, content, **_):
        assert schema is RequirementAssessment
        self.payload = json.loads(content[0]["text"])
        return RequirementAssessment(
            reply="已知道是婚禮。請問季節和場地是在室內還是戶外？",
            occasions=["wedding"],
            seasons=[],
            times_of_day=[],
            climates=[],
            formalities=["formal"],
            activities=[],
            styles=[],
            special_requirements=["avoid drawing attention"],
            additional_notes="",
            search_brief="參加婚禮，穿搭避免過度搶眼",
            missing_fields=["seasons", "climates", "seasons"],
            ready_to_plan=False,
        )


def test_requirement_collector_only_uses_current_conversation() -> None:
    llm = FakeRequirementLLM()
    result = RequirementCollector(llm).collect(
        [ChatTurn(role="user", text="我要參加婚禮，不想穿得太搶眼")]
    )

    assert result.requirements.occasions == ["wedding"]
    assert result.missing_fields == ["seasons", "climates"]
    assert result.ready_to_plan is False
    assert set(llm.payload) == {"conversation", "audience"}


def test_planner_context_includes_profile_hard_rules_and_all_active_memories() -> None:
    profile = UserHardRule(
        user_key="demo",
        gender="female",
        age=28,
        height_cm=165.5,
        weight_kg=55.0,
        avoid_colours=["yellow"],
    )
    memory = UserStylePreference(
        user_key="demo",
        preference_text="戶外晚宴時喜歡俐落襯衫與寬褲",
        occasions=["outdoor dinner"],
        seasons=["autumn"],
        activities=["walking on grass"],
        is_active=True,
    )

    context = build_planner_preference_context(profile, [memory])

    assert context["user_profile"]["height_cm"] == 165.5
    assert context["hard_rules"]["avoid_colours"] == ["yellow"]
    assert context["outfit_memories"][0]["preference_sentence"] == memory.preference_text


def query_rows(*, chinese: bool = False) -> list[PlannedCatalogQuery]:
    rows = []
    for index in range(5):
        rows.append(
            PlannedCatalogQuery(
                garment_zone="upper_body",
                text=(f"白色輕盈上衣 {index}" if chinese else f"structured black satin blouse style {index}"),
                rationale=f"上身方向 {index}",
            )
        )
    for index in range(5):
        rows.append(
            PlannedCatalogQuery(
                garment_zone="lower_body",
                text=(f"黑色俐落長褲 {index}" if chinese else f"tailored black wide leg trousers style {index}"),
                rationale=f"下身方向 {index}",
            )
        )
    for index in range(2):
        rows.append(
            PlannedCatalogQuery(
                garment_zone="one_piece",
                text=(f"黑色正式洋裝 {index}" if chinese else f"elegant black satin midi dress style {index}"),
                rationale=f"套裝方向 {index}",
            )
        )
    return rows


def repaired_rows() -> list[RepairedCatalogQuery]:
    return [
        RepairedCatalogQuery(
            garment_zone=row.garment_zone,
            text=f"clean visual garment style {index}",
        )
        for index, row in enumerate(query_rows())
    ]


class FakeLLM:
    def __init__(self, *, chinese: bool = False, fail_repair: bool = False):
        self.chinese = chinese
        self.fail_repair = fail_repair
        self.payloads = []

    def parse(self, *, schema, content, **_):
        self.payloads.append(json.loads(content[0]["text"]))
        if schema is EnglishQueryRepair:
            if self.fail_repair:
                raise RuntimeError("repair unavailable")
            return EnglishQueryRepair(queries=repaired_rows())
        return KnowledgeQueryDraft(
            context_restrictiveness="high",
            hard_constraints=["維持正式感"],
            aesthetic_direction=["俐落"],
            queries=query_rows(chinese=self.chinese),
            planning_note="已檢查搜尋方向。",
        )


def test_planner_returns_five_five_two_without_article_knowledge() -> None:
    llm = FakeLLM()
    memory = UserStylePreference(
        user_key="demo",
        preference_text="相似晚宴情境曾選擇絲緞上衣與寬褲",
        is_active=True,
    )

    result = QueryPlanner(llm).plan(
        "女生參加正式晚宴",
        audience="women",
        style_preferences=[memory],
    )

    assert Counter(query.garment_zone for query in result.queries) == {
        "upper_body": 5,
        "lower_body": 5,
        "one_piece": 2,
    }
    assert "retrieved_observations" not in llm.payloads[0]
    assert len(llm.payloads[0]["user_preferences"]["outfit_memories"]) == 1
    assert result.knowledge_observation_ids == []
    assert all(not query.references for query in result.queries)


def test_chinese_queries_are_repaired_to_twelve_english_queries() -> None:
    llm = FakeLLM(chinese=True)

    result = QueryPlanner(llm).plan("去海邊玩 女生", audience="women")

    assert len(llm.payloads) == 2
    assert len(result.queries) == 12
    assert all(query.text.isascii() for query in result.queries)


def test_failed_query_repair_uses_safe_fallbacks_for_all_zones() -> None:
    llm = FakeLLM(chinese=True, fail_repair=True)

    result = QueryPlanner(llm).plan("去海邊玩 女生", audience="women")

    assert len(result.queries) == 12
    assert all(query.text.isascii() for query in result.queries)


def test_explicit_user_color_is_preserved() -> None:
    result = QueryPlanner(FakeLLM()).plan(
        "女生參加正式晚宴，想穿黑色",
        audience="women",
    )

    assert any("black" in query.text.lower() for query in result.queries)


def test_beach_query_removes_denim_unless_user_requests_it() -> None:
    normalizer = QueryOutputNormalizer(FakeLLM())

    assert normalizer._remove_contextually_unsuitable_terms(
        "relaxed denim shorts", "去海邊玩"
    ) == "relaxed shorts"
    assert normalizer._remove_contextually_unsuitable_terms(
        "relaxed denim shorts", "去海邊玩，想穿牛仔短褲"
    ) == "relaxed denim shorts"
