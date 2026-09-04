import json
from collections import Counter

from app.models.user_preference import UserHardRule, UserStylePreference
from app.preferences.context import build_planner_preference_context
from app.schemas import ChatTurn, PairingDirection, RequirementSummary, StylingGuide
from app.services.query_planner import (
    EnglishQueryRepair,
    KnowledgeQueryDraft,
    PlannedCatalogQuery,
    QueryOutputNormalizer,
    QueryPlanner,
    RepairedCatalogQuery,
    RequirementAssessment,
    RequirementCollector,
    TagTranslation,
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
            updated_fields=["occasions", "formalities", "special_requirements"],
            tag_translations=[
                TagTranslation(tag="wedding", label_zh="婚禮"),
                TagTranslation(tag="formal", label_zh="正式"),
                TagTranslation(tag="avoid drawing attention", label_zh="避免過度搶眼"),
            ],
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
    assert set(llm.payload) == {"conversation", "audience", "previous_requirements"}


class FakeUpdateRequirementLLM:
    def parse(self, **_):
        return RequirementAssessment(
            reply="已補上戶外環境。",
            climates=["outdoor"],
            search_brief="秋季戶外婚禮穿搭",
            updated_fields=["climates"],
            tag_translations=[TagTranslation(tag="outdoor", label_zh="戶外")],
            ready_to_plan=True,
        )


def test_requirement_update_preserves_fields_not_mentioned_this_turn() -> None:
    previous = RequirementSummary(
        occasions=["wedding"],
        seasons=["autumn"],
        tag_translations={"wedding": "婚禮", "autumn": "秋季"},
    )

    result = RequirementCollector(FakeUpdateRequirementLLM()).collect(
        [ChatTurn(role="user", text="場地在戶外")],
        previous_requirements=previous,
    )

    assert result.requirements.occasions == ["wedding"]
    assert result.requirements.seasons == ["autumn"]
    assert result.requirements.climates == ["outdoor"]
    assert result.requirements.tag_translations["wedding"] == "婚禮"


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
                direction_id="ABCDE"[index],
                text=(f"白色輕盈上衣 {index}" if chinese else f"structured black satin blouse style {index}"),
                rationale=f"上身方向 {index}",
            )
        )
    for index in range(5):
        rows.append(
            PlannedCatalogQuery(
                garment_zone="lower_body",
                direction_id="ABCDE"[index],
                text=(f"黑色俐落長褲 {index}" if chinese else f"tailored black wide leg trousers style {index}"),
                rationale=f"下身方向 {index}",
            )
        )
    for index in range(2):
        rows.append(
            PlannedCatalogQuery(
                garment_zone="one_piece",
                direction_id="FG"[index],
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
            excluded_query_terms=["black"] if self.chinese else [],
            aesthetic_direction=["俐落"],
            styling_guide=StylingGuide(
                concept="Concrete visual interpretation",
                visual_attributes=["high-saturation color blocking"],
                avoid_misinterpretations=["Do not infer floral print from colorful"],
                color_direction=["vivid contrasting tones"],
                silhouette_direction=["fitted top with relaxed lower body"],
                material_direction=["smooth lightweight surfaces"],
                pattern_direction=["clean color blocking"],
                pairing_directions=[
                    PairingDirection(
                        id=direction_id,
                        concept=f"Direction {direction_id}",
                        upper_body_focus="fitted upper body",
                        lower_body_focus="relaxed lower body",
                        color_relationship="deliberate tonal contrast",
                    )
                    for direction_id in "ABCDE"
                ],
                reviewer_checklist=["Judge visible proportions, not style keywords"],
            ),
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
    assert result.styling_guide is not None
    assert [query.direction_id for query in result.queries[:5]] == list("ABCDE")


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


def test_rejected_concepts_are_removed_before_embedding_search() -> None:
    normalizer = QueryOutputNormalizer(FakeLLM())
    forbidden = normalizer._forbidden_query_terms(
        "我不要裙子和牛仔，但喜歡寬鬆剪裁", None, None, None
    )

    assert "skirt" in forbidden
    assert "denim" in forbidden
    assert "oversized" not in forbidden
    assert normalizer._remove_forbidden_terms(
        "relaxed denim skirt without stripes", forbidden | {"stripes"}
    ) == "relaxed"


def test_refinement_rejections_are_removed_from_embedding_queries() -> None:
    result = QueryPlanner(FakeLLM()).plan(
        "女生參加正式晚宴",
        audience="women",
        refinement="不要黑色，也不要裙子",
    )

    assert all("black" not in query.text.lower() for query in result.queries)
    assert all("skirt" not in query.text.lower() for query in result.queries)
