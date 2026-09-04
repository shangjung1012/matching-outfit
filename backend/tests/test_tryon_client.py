from importlib import import_module

import httpx
import pytest

from app.core.config import Settings


def load_tryon_client_module():
    try:
        return import_module("app.services.tryon_client")
    except ModuleNotFoundError:
        pytest.fail("the generic app.services.tryon_client module does not exist")


def test_settings_use_only_tryon_environment_names(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "TRYON_API_URL",
        "TRYON_API_KEY",
        "TRYON_REQUEST_TIMEOUT_SECONDS",
        "CATVTON_API_URL",
        "CATVTON_API_KEY",
        "CATVTON_REQUEST_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TRYON_API_URL", "https://tryon.example/")
    monkeypatch.setenv("TRYON_API_KEY", "tryon-secret")
    monkeypatch.setenv("TRYON_REQUEST_TIMEOUT_SECONDS", "42")

    configured = Settings(_env_file=None)

    assert configured.tryon_api_url == "https://tryon.example/"
    assert configured.tryon_api_key == "tryon-secret"
    assert configured.tryon_request_timeout_seconds == 42.0
    assert not hasattr(configured, "catvton_api_url")
    assert not hasattr(configured, "catvton_api_key")
    assert not hasattr(configured, "catvton_request_timeout_seconds")

    monkeypatch.delenv("TRYON_API_URL")
    monkeypatch.delenv("TRYON_API_KEY")
    monkeypatch.delenv("TRYON_REQUEST_TIMEOUT_SECONDS")
    monkeypatch.setenv("CATVTON_API_URL", "https://legacy.example/")
    monkeypatch.setenv("CATVTON_API_KEY", "legacy-secret")
    monkeypatch.setenv("CATVTON_REQUEST_TIMEOUT_SECONDS", "99")

    legacy_only = Settings(_env_file=None)

    assert legacy_only.tryon_api_url == ""
    assert legacy_only.tryon_api_key == ""
    assert legacy_only.tryon_request_timeout_seconds == 300.0


def test_client_forwards_canonical_multipart_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_tryon_client_module()
    monkeypatch.setattr(module.settings, "tryon_api_url", "https://tryon.example/")
    monkeypatch.setattr(module.settings, "tryon_api_key", "tryon-secret")
    captured: dict = {}

    def fake_request(method: str, url: str, **kwargs) -> httpx.Response:
        captured.update(method=method, url=url, **kwargs)
        request = httpx.Request(method, url)
        return httpx.Response(
            202,
            json={"id": "f1cb2481-588d-4a66-937e-7149b81e268c"},
            request=request,
        )

    monkeypatch.setattr(module.httpx, "request", fake_request)
    client = module.TryOnClient()

    result = client.create_job(
        b"person-bytes",
        "image/png",
        {
            "upper": (b"upper-bytes", "image/png"),
            "shoe": (b"shoe-bytes", "image/webp"),
            "bag": (b"bag-bytes", "image/jpeg"),
        },
    )

    assert result == {"id": "f1cb2481-588d-4a66-937e-7149b81e268c"}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://tryon.example/v1/jobs"
    assert captured["headers"] == {"X-API-Key": "tryon-secret"}
    assert list(captured["files"]) == [
        "person_image",
        "upper_image",
        "shoe_image",
        "bag_image",
    ]
    assert {
        name: (value[1].read(), value[2])
        for name, value in captured["files"].items()
    } == {
        "person_image": (b"person-bytes", "image/png"),
        "upper_image": (b"upper-bytes", "image/png"),
        "shoe_image": (b"shoe-bytes", "image/webp"),
        "bag_image": (b"bag-bytes", "image/jpeg"),
    }


def test_generic_client_symbols_replace_catvton_symbols() -> None:
    module = load_tryon_client_module()

    assert module.TryOnClient is not None
    assert module.TryOnError is not None
    assert isinstance(module.tryon_client, module.TryOnClient)
    assert not hasattr(module, "CatVTONClient")
    assert not hasattr(module, "CatVTONError")
    assert not hasattr(module, "catvton_client")
