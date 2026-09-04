from app.schemas.fashion_knowledge import OutfitObservation
from app.services.query_planner import (
    EnglishQueryRepair,
    KnowledgeQueryDraft,
    QueryPlanner,
    QueryOutputNormalizer,
    PlannedCatalogQuery,
    RepairedCatalogQuery,
)


class FakeLLM:
    def parse(self, *, schema, **_):
        if schema is EnglishQueryRepair:
            return EnglishQueryRepair(
                queries=[
                    RepairedCatalogQuery(
                        garment_zone="upper_body",
                        text="structured ivory satin blouse minimal details",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="upper_body",
                        text="minimal ivory draped satin top",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="lower_body",
                        text="tailored black high-waisted trousers feminine silhouette",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="lower_body",
                        text="flowing black midi skirt elegant silhouette",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="one_piece",
                        text="elegant black satin midi dress structured silhouette",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="one_piece",
                        text="minimal black wide-leg jumpsuit refined drape",
                    ),
                ]
            )
        return KnowledgeQueryDraft(
            context_restrictiveness="high",
            hard_constraints=["維持正式感"],
            aesthetic_direction=["俐落", "低彩度"],
            queries=[
                PlannedCatalogQuery(
                    garment_zone="lower_body",
                    text="tailored black high-waisted trousers 柔美線條",
                    rationale="與俐落上衣形成正式套裝感",
                ),
                PlannedCatalogQuery(
                    garment_zone="one_piece",
                    text="elegant black satin midi dress structured silhouette",
                    rationale="作為完整的正式洋裝方向",
                ),
                PlannedCatalogQuery(
                    garment_zone="upper_body",
                    text="structured ivory satin blouse minimal details",
                    rationale="維持精緻且不搶眼的上身重點",
                    cited_observation_ids=["obs_valid", "obs_not_supplied"],
                ),
                PlannedCatalogQuery(
                    garment_zone="upper_body",
                    text="minimal ivory draped satin top",
                    rationale="提供較柔和但正式的替代上衣",
                ),
                PlannedCatalogQuery(
                    garment_zone="lower_body",
                    text="flowing black midi skirt elegant silhouette",
                    rationale="提供裙裝搭配方向",
                ),
                PlannedCatalogQuery(
                    garment_zone="one_piece",
                    text="minimal black wide-leg jumpsuit refined drape",
                    rationale="提供連身褲替代方向",
                ),
            ],
            cited_observation_ids=["obs_valid", "obs_not_supplied"],
            planning_note="已檢查三區搜尋句與上下身相容性。",
        )


def test_agent_plan_orders_zones_and_filters_citations() -> None:
    observation = OutfitObservation(
        observation_id="obs_valid",
        summary="正式晚宴可使用俐落剪裁與帶光澤材質",
        evidence="絲緞與結構剪裁",
        audiences=["women"],
        occasions=["正式晚宴"],
        signal_type="timeless",
        confidence=0.9,
        source_url="https://example.com/formal-style",
    )
    planner = QueryPlanner(FakeLLM())

    result = planner.plan(
        "女生參加正式晚宴",
        [observation],
        audience="women",
    )

    assert result.planner == "knowledge-agent-v1"
    assert result.audience == "women"
    assert [query.garment_zone for query in result.queries] == [
        "upper_body",
        "upper_body",
        "lower_body",
        "lower_body",
        "one_piece",
        "one_piece",
    ]
    assert result.knowledge_observation_ids == ["obs_valid"]
    assert result.queries[0].knowledge_observation_ids == ["obs_valid"]
    assert result.queries[0].source_urls == ["https://example.com/formal-style"]
    assert result.queries[1].source_urls == []
    assert result.queries[2].text == "tailored high-waisted trousers feminine silhouette"
    assert all("black" not in query.text.lower() for query in result.queries)
    assert "已自動正規化為英文" in (result.planning_note or "")


class ChineseOnlyLLM:
    def __init__(self, fail_repair: bool = False):
        self.fail_repair = fail_repair
        self.calls = 0

    def parse(self, *, schema, **_):
        self.calls += 1
        if schema is EnglishQueryRepair:
            if self.fail_repair:
                raise RuntimeError("repair unavailable")
            return EnglishQueryRepair(
                queries=[
                    RepairedCatalogQuery(
                        garment_zone="upper_body",
                        text="airy white linen relaxed-fit blouse",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="upper_body",
                        text="breathable pastel sleeveless draped top",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="lower_body",
                        text="light blue flowing wide-leg trousers",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="lower_body",
                        text="bright relaxed lightweight midi skirt",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="one_piece",
                        text="breezy white cotton midi sundress",
                    ),
                    RepairedCatalogQuery(
                        garment_zone="one_piece",
                        text="colorful relaxed A-line sundress",
                    ),
                ]
            )
        return KnowledgeQueryDraft(
            context_restrictiveness="low",
            aesthetic_direction=["輕盈", "清爽"],
            queries=[
                PlannedCatalogQuery(
                    garment_zone="upper_body",
                    text="白色寬鬆亞麻上衣",
                    rationale="輕盈透氣",
                ),
                PlannedCatalogQuery(
                    garment_zone="upper_body",
                    text="亮色無袖垂墜上衣",
                    rationale="提供另一種清爽輪廓",
                ),
                PlannedCatalogQuery(
                    garment_zone="lower_body",
                    text="淺藍色飄逸寬褲",
                    rationale="與白色上衣協調",
                ),
                PlannedCatalogQuery(
                    garment_zone="lower_body",
                    text="亮色輕盈中長裙",
                    rationale="提供裙裝方向",
                ),
                PlannedCatalogQuery(
                    garment_zone="one_piece",
                    text="白色棉質中長洋裝",
                    rationale="完整替代方案",
                ),
                PlannedCatalogQuery(
                    garment_zone="one_piece",
                    text="多彩寬鬆A字洋裝",
                    rationale="提供不同的完整替代方案",
                ),
            ],
            cited_observation_ids=["obs_valid"],
            planning_note="已依海邊需求規劃。",
        )


def _observation() -> OutfitObservation:
    return OutfitObservation(
        observation_id="obs_valid",
        summary="海邊穿搭可選擇輕盈透氣材質",
        evidence="亞麻與棉質單品",
        audiences=["women"],
        occasions=["海邊"],
        signal_type="timeless",
        confidence=0.9,
    )


def test_chinese_queries_are_repaired_without_losing_knowledge() -> None:
    llm = ChineseOnlyLLM()
    result = QueryPlanner(llm).plan(
        "去海邊玩 女生", [_observation()], audience="women"
    )

    assert llm.calls == 2
    assert result.planner == "knowledge-agent-v1"
    assert result.knowledge_observation_ids == ["obs_valid"]
    assert all(query.text.isascii() for query in result.queries)


def test_failed_query_repair_uses_safe_fallback_without_losing_knowledge() -> None:
    llm = ChineseOnlyLLM(fail_repair=True)
    result = QueryPlanner(llm).plan(
        "去海邊玩 女生", [_observation()], audience="women"
    )

    assert result.planner == "knowledge-agent-v1"
    assert result.knowledge_observation_ids == ["obs_valid"]
    assert all(query.text.isascii() for query in result.queries)


def test_explicit_user_color_is_preserved() -> None:
    result = QueryPlanner(FakeLLM()).plan(
        "女生參加正式晚宴，想穿黑色", [_observation()], audience="women"
    )

    assert "black" in result.queries[2].text.lower()


def test_beach_query_removes_denim_unless_user_requests_it() -> None:
    normalizer = QueryOutputNormalizer(FakeLLM())

    assert normalizer._remove_contextually_unsuitable_terms(
        "relaxed denim shorts", "去海邊玩"
    ) == "relaxed shorts"
    assert normalizer._remove_contextually_unsuitable_terms(
        "relaxed denim shorts", "去海邊玩，想穿牛仔短褲"
    ) == "relaxed denim shorts"
