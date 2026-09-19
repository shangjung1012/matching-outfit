from importlib import import_module

import httpx


def test_client_derives_human3d_route_from_tryon_url_and_key(monkeypatch) -> None:
    module = import_module("app.services.human3d_client")
    monkeypatch.setattr(module.settings, "tryon_api_url", "https://gpu.example/")
    monkeypatch.setattr(module.settings, "tryon_api_key", "shared-secret")
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
    client = module.Human3DClient()

    payload = client.create_job(b"image-bytes", "image/png")

    assert payload["id"] == "f1cb2481-588d-4a66-937e-7149b81e268c"
    assert captured["url"] == "https://gpu.example/human3d/v1/jobs"
    assert captured["headers"] == {"X-API-Key": "shared-secret"}
    filename, stream, content_type = captured["files"]["image"]
    assert filename == "try-on-result.png"
    assert stream.read() == b"image-bytes"
    assert content_type == "image/png"


def test_health_is_unavailable_when_shared_tryon_entrypoint_is_unset(monkeypatch) -> None:
    module = import_module("app.services.human3d_client")
    monkeypatch.setattr(module.settings, "tryon_api_url", "")
    monkeypatch.setattr(module.settings, "tryon_api_key", "")

    available, reason = module.Human3DClient().health()

    assert available is False
    assert reason == "TryOn API 尚未設定"
