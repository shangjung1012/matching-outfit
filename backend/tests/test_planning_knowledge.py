from app.api import routes
from app.schemas.fashion_knowledge import OutfitObservation
from app.schemas.workflow import RequirementSummary
from app.services.query_planner import QueryPlanner
from tests.test_query_planner import FakeLLM


def observation():
    return OutfitObservation(observation_id="known", summary="短上衣配高腰下裝",
                             evidence="以長短對比建立造型比例", source_url="https://www.elle.com/example",
                             signal_type="timeless", confidence=0.9)


class KnowledgeLLM(FakeLLM):
    def parse(self, **kwargs):
        draft = super().parse(**kwargs)
        return draft.model_copy(update={"cited_observation_ids": ["known", "invented", "known"],
                                        "knowledge_gaps": [], "knowledge_note": "採用比例原則"})


def test_planner_uses_only_supplied_knowledge_and_exposes_trace():
    llm = KnowledgeLLM()
    result = QueryPlanner(llm).plan("棕白色女團舞", observations=[observation()], include_debug=True)
    assert llm.payloads[0]["retrieved_observations"][0]["observation_id"] == "known"
    assert result.knowledge_observation_ids == ["known"]
    assert result.knowledge_observations == [observation()]
    assert result.knowledge_gaps == []
    assert result.debug.knowledge_used_ids == ["known"]


def test_missing_knowledge_records_request_specific_gap():
    result = QueryPlanner(FakeLLM()).plan("棕白色女團舞", include_debug=True)
    assert "棕白色女團舞" in result.knowledge_gaps[0]
    assert result.debug.knowledge_gaps == result.knowledge_gaps


def test_retrieval_failure_is_not_a_confirmed_gap(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("embedding unavailable")
    monkeypatch.setattr(routes, "semantic_fashion_knowledge", fail)
    observations, note = routes.planning_knowledge(None, "原始精確風格", RequirementSummary(), None)
    assert observations == [] and "不是已確認" in note
    result = QueryPlanner(FakeLLM()).plan("女團舞", knowledge_retrieval_note=note)
    assert "非確定缺口" in result.knowledge_gaps[0]


def test_knowledge_query_retains_raw_request(monkeypatch):
    queries = []
    def retrieve(db, query, **kwargs):
        queries.append(query)
        return [observation()]
    monkeypatch.setattr(routes, "semantic_fashion_knowledge", retrieve)
    items, note = routes.planning_knowledge(None, "復古千禧年女團", RequirementSummary(location="台灣"), "women")
    assert "復古千禧年女團" in queries[0]
    assert items and not note
