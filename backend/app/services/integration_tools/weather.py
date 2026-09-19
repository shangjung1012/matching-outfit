"""Date-specific forecast evidence; never substitute seasonal stereotypes for data."""

from datetime import date, datetime, timezone
from functools import lru_cache
import logging
import time

import httpx

from app.schemas.workflow import RequirementSummary, WeatherContext
from app.services.requirement_context import current_taiwan_context

logger = logging.getLogger(__name__)
# A country is not a precise weather location. Make this fallback explicit in UI.
TAIWAN_CITIES = {
    "台北": (25.033, 121.5654), "臺北": (25.033, 121.5654),
    "新竹": (24.8138, 120.9675),
    "台中": (24.1477, 120.6736), "臺中": (24.1477, 120.6736),
    "台南": (22.9999, 120.2269), "臺南": (22.9999, 120.2269),
    "高雄": (22.6273, 120.3014), "花蓮": (23.9872, 121.6015),
    "台東": (22.7554, 121.1500), "臺東": (22.7554, 121.1500),
    "墾丁": (21.945, 120.798), "宜蘭": (24.757, 121.753),
}


def _resolve_location(client, location):
    if location.lower() in {"台灣", "臺灣", "taiwan"}:
        return "新竹（未指定城市，暫用參考點）", 24.8138, 120.9675, True
    city = location.removesuffix("市").removesuffix("縣")
    if city in TAIWAN_CITIES:
        return location, *TAIWAN_CITIES[city], False
    response = client.get("https://geocoding-api.open-meteo.com/v1/search",
                          params={"name": location, "count": 5, "language": "zh", "format": "json"})
    response.raise_for_status()
    matches = response.json().get("results", [])
    if len(matches) != 1:
        raise ValueError("地點不明確或找不到，請提供城市名稱；不會擅自套用其他城市氣溫")
    match = matches[0]
    return f"{match['name']}／{match.get('country', '')}", match["latitude"], match["longitude"], False


@lru_cache(maxsize=256)
def _forecast(location: str, target_date: str, cache_hour: int) -> WeatherContext:
    with httpx.Client(timeout=5.0, follow_redirects=False) as client:
        name, latitude, longitude, assumed = _resolve_location(client, location)
        response = client.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": latitude, "longitude": longitude, "timezone": "auto",
            "start_date": target_date, "end_date": target_date,
            "daily": "temperature_2m_min,temperature_2m_max,apparent_temperature_min,apparent_temperature_max,precipitation_probability_max",
        })
        response.raise_for_status()
        daily = response.json()["daily"]
        if daily["time"][0] != target_date:
            raise ValueError("天氣回覆日期與需求不一致")
        def value(key):
            result = daily[key][0]
            return None if result is None else float(result)
        low, high = value("temperature_2m_min"), value("temperature_2m_max")
        if low is None or high is None:
            raise ValueError("天氣資料缺少氣溫")
        return WeatherContext(
            status="available", location=name, target_date=target_date, location_assumed=assumed,
            temperature_min_c=low, temperature_max_c=high,
            apparent_temperature_min_c=value("apparent_temperature_min"),
            apparent_temperature_max_c=value("apparent_temperature_max"),
            precipitation_probability_max=value("precipitation_probability_max"),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            note="當日整天預報範圍，不是即時觀測或出門時段氣溫；請以氣溫／體感優先，不因秋季就強制長袖。",
        )


def with_weather_context(summary: RequirementSummary) -> RequirementSummary:
    # Discard client-supplied/stale weather whenever location or date changes.
    result = summary.model_copy(deep=True)
    result.weather = WeatherContext(location=summary.location, target_date=summary.target_date)
    try:
        if not summary.target_date:
            raise ValueError("僅指定季節、沒有日期，無法查該日預報；不拿今日氣溫套用其他季節")
        target = date.fromisoformat(summary.target_date)
        today = date.fromisoformat(current_taiwan_context()["today"])
        if not 0 <= (target - today).days <= 15:
            raise ValueError("日期不在未來 16 日預報範圍，不會捏造氣溫；可補充預期溫度")
        result.weather = _forecast(summary.location, summary.target_date, int(time.time() // 3600)).model_copy(deep=True)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
        result.weather.note = f"天氣未取得：{error}。季節不能當作實際氣溫，避免無根據地強制厚薄或袖長。"
        logger.warning("weather_context_unavailable: %s", error)
    return result
