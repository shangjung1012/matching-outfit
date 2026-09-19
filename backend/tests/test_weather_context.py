from datetime import date, timedelta

import httpx

from app.schemas.workflow import RequirementSummary, WeatherContext
from app.services.integration_tools import weather
from app.services.requirement_context import with_context_defaults, current_taiwan_context


def test_hot_autumn_weather_is_available_without_overwriting_user_climate(monkeypatch):
    today = current_taiwan_context()["today"]
    summary = with_context_defaults(RequirementSummary(target_date=today, climates=["air conditioned"]))
    monkeypatch.setattr(weather, "_forecast", lambda *args: WeatherContext(
        status="available", location="台北", target_date=today,
        temperature_min_c=27, temperature_max_c=34,
        apparent_temperature_max_c=39))
    result = weather.with_weather_context(summary)
    assert result.weather.temperature_max_c == 34
    assert result.climates == ["air conditioned"]
    assert summary.weather is None


def test_default_taiwan_weather_point_is_labelled():
    location, lat, lon, assumed = weather._resolve_location(None, "台灣")
    assert assumed and "新竹" in location
    assert lat == 24.8138
    assert lon == 120.9675


def test_city_and_destination_change_resolve_separately():
    assert weather._resolve_location(None, "高雄市")[1] == 22.6273
    assert weather._resolve_location(None, "墾丁")[1] == 21.945


def test_season_only_and_out_of_range_never_fetch_forecast(monkeypatch):
    def unexpected(*args):
        raise AssertionError("should not fetch")
    monkeypatch.setattr(weather, "_forecast", unexpected)
    season = weather.with_weather_context(with_context_defaults(RequirementSummary(seasons=["winter"])))
    assert season.weather.status == "unavailable"
    future = (date.fromisoformat(current_taiwan_context()["today"]) + timedelta(days=30)).isoformat()
    result = weather.with_weather_context(RequirementSummary(location="台北", target_date=future))
    assert result.weather.temperature_max_c is None
    assert "16" in result.weather.note


def test_network_failure_clears_stale_weather(monkeypatch):
    def fail(*args):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(weather, "_forecast", fail)
    summary = with_context_defaults(None)
    summary.weather = WeatherContext(status="available", temperature_max_c=10)
    result = weather.with_weather_context(summary)
    assert result.weather.status == "unavailable"
    assert result.weather.temperature_max_c is None
    assert "offline" in result.weather.note


def test_forecast_request_and_response(monkeypatch):
    today = current_taiwan_context()["today"]
    captured = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, params):
            captured.append(params)
            return httpx.Response(200, request=httpx.Request("GET", url), json={"daily": {
                "time": [today], "temperature_2m_min": [27], "temperature_2m_max": [34],
                "apparent_temperature_min": [29], "apparent_temperature_max": [39],
                "precipitation_probability_max": [20]}})
    monkeypatch.setattr(weather.httpx, "Client", Client)
    weather._forecast.cache_clear()
    try:
        result = weather._forecast("高雄", today, 1)
        assert result.temperature_max_c == 34
        assert captured[0]["start_date"] == today
        assert captured[0]["latitude"] == 22.6273
        assert captured[0]["timezone"] == "auto"
    finally:
        weather._forecast.cache_clear()
