from io import BytesIO
import uuid

import httpx

from app.core.config import settings


REFERENCE_TYPES = ("upper", "lower", "overall", "shoe", "bag")


class TryOnError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class TryOnClient:
    def __init__(self) -> None:
        self.base_url = settings.tryon_api_url.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": settings.tryon_api_key}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.base_url:
            raise TryOnError("TryOn API 尚未設定")
        timeout = kwargs.pop(
            "timeout",
            httpx.Timeout(settings.tryon_request_timeout_seconds, connect=10.0),
        )
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                timeout=timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as error:
            detail = error.response.text[:500]
            raise TryOnError(
                f"TryOn 回傳 {error.response.status_code}: {detail}",
                status_code=error.response.status_code,
            ) from error
        except httpx.HTTPError as error:
            raise TryOnError(f"TryOn 請求失敗：{error}") from error

    def health(self) -> tuple[bool, str | None]:
        try:
            payload = self._request("GET", "/health", timeout=5.0).json()
        except (TryOnError, ValueError) as error:
            return False, str(error)
        if payload.get("status") != "ready":
            return False, str(payload.get("reason") or "TryOn 模型尚未就緒")
        return True, None

    def create_job(
        self,
        person_content: bytes,
        person_content_type: str,
        references: dict[str, tuple[bytes, str]],
    ) -> dict:
        files = {
            "person_image": ("person", BytesIO(person_content), person_content_type),
        }
        for reference_type in REFERENCE_TYPES:
            reference = references.get(reference_type)
            if reference is None:
                continue
            content, content_type = reference
            files[f"{reference_type}_image"] = (
                reference_type,
                BytesIO(content),
                content_type,
            )
        response = self._request("POST", "/v1/jobs", files=files)
        try:
            return response.json()
        except ValueError as error:
            raise TryOnError("TryOn 建立工作時回傳無效資料") from error

    def get_job(self, remote_job_id: uuid.UUID) -> dict:
        try:
            return self._request("GET", f"/v1/jobs/{remote_job_id}").json()
        except ValueError as error:
            raise TryOnError("TryOn 工作狀態格式無效") from error

    def get_result(self, remote_job_id: uuid.UUID) -> tuple[bytes, str]:
        response = self._request("GET", f"/v1/jobs/{remote_job_id}/result")
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            raise TryOnError("TryOn 未回傳圖片")
        return response.content, content_type

    def delete_job(self, remote_job_id: uuid.UUID) -> None:
        self._request("DELETE", f"/v1/jobs/{remote_job_id}")


tryon_client = TryOnClient()
