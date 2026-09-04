from app.schemas.styling import OutfitObservation
from app.services.fashion_knowledge import retrieve_observations


def observation(identifier: str, summary: str, occasions: list[str]) -> OutfitObservation:
    return OutfitObservation(
        observation_id=identifier,
        summary=summary,
        evidence="測試資料",
        occasions=occasions,
        signal_type="timeless",
        confidence=0.8,
    )


def test_retrieval_prefers_contextual_overlap() -> None:
    beach = observation("beach", "透氣材質與寬鬆輪廓適合炎熱海邊", ["海邊度假"])
    gala = observation("gala", "正式晚宴使用深色俐落剪裁", ["晚宴"])

    results = retrieve_observations("我要去海邊度假，希望清爽好看", [gala, beach], 1)

    assert results[0].observation_id == "beach"


def test_retrieval_has_confidence_fallback_for_unseen_request() -> None:
    low = observation("low", "低信心資料", [])
    low.confidence = 0.2
    high = observation("high", "高信心資料", [])

    results = retrieve_observations("完全沒有重疊詞彙", [low, high], 1)

    assert results[0].observation_id == "high"
