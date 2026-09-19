from __future__ import annotations

import os

import httpx


class FastFitControlError(RuntimeError):
    pass


class FastFitControlClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (
            base_url if base_url is not None else os.getenv("FASTFIT_CONTROL_URL", "")
        ).rstrip("/")
        self.api_key = (
            api_key
            if api_key is not None
            else os.getenv("FASTFIT_CONTROL_API_KEY", "")
        )

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}

    def _request(self, method: str, path: str) -> httpx.Response:
        if not self.base_url or not self.api_key:
            raise FastFitControlError(
                "FASTFIT_CONTROL_URL and FASTFIT_CONTROL_API_KEY are required "
                "for lazy switching"
            )
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                timeout=300.0,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPError as error:
            raise FastFitControlError(f"FastFit model control failed: {error}") from error

    def health(self) -> dict:
        try:
            return self._request("GET", "/health").json()
        except ValueError as error:
            raise FastFitControlError("FastFit health response is invalid") from error

    def unload(self) -> None:
        self._request("POST", "/v1/model/unload")

    def load(self) -> None:
        self._request("POST", "/v1/model/load")
