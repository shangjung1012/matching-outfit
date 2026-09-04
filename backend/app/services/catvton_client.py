from io import BytesIO
import uuid

import httpx

from app.core.config import settings


class CatVTONError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class CatVTONClient:
    def __init__(self) -> None:
        self.base_url = settings.catvton_api_url.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": settings.catvton_api_key}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.base_url:
            raise CatVTONError("CatVTON API 尚未設定")
        timeout = kwargs.pop(
            "timeout",
            httpx.Timeout(settings.catvton_request_timeout_seconds, connect=10.0),
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
            raise CatVTONError(
                f"CatVTON 回傳 {error.response.status_code}: {detail}",
                status_code=error.response.status_code,
            ) from error
        except httpx.HTTPError as error:
            raise CatVTONError(f"CatVTON 請求失敗：{error}") from error

    def health(self) -> tuple[bool, str | None]:
        try:
            payload = self._request("GET", "/health", timeout=5.0).json()
        except (CatVTONError, ValueError) as error:
            return False, str(error)
        if payload.get("status") != "ready":
            return False, str(payload.get("reason") or "CatVTON 模型尚未就緒")
        return True, None

    def create_job(
        self,
        person_content: bytes,
        person_content_type: str,
        cloth_content: bytes,
        cloth_content_type: str,
        cloth_type: str,
    ) -> dict:
        response = self._request(
            "POST",
            "/v1/jobs",
            files={
                "person_image": ("person", BytesIO(person_content), person_content_type),
                "cloth_image": ("cloth", BytesIO(cloth_content), cloth_content_type),
            },
            data={"cloth_type": cloth_type},
        )
        try:
            return response.json()
        except ValueError as error:
            raise CatVTONError("CatVTON 建立工作時回傳無效資料") from error

    def get_job(self, remote_job_id: uuid.UUID) -> dict:
        try:
            return self._request("GET", f"/v1/jobs/{remote_job_id}").json()
        except ValueError as error:
            raise CatVTONError("CatVTON 工作狀態格式無效") from error

    def get_result(self, remote_job_id: uuid.UUID) -> tuple[bytes, str]:
        response = self._request("GET", f"/v1/jobs/{remote_job_id}/result")
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            raise CatVTONError("CatVTON 未回傳圖片")
        return response.content, content_type

    def delete_job(self, remote_job_id: uuid.UUID) -> None:
        self._request("DELETE", f"/v1/jobs/{remote_job_id}")


catvton_client = CatVTONClient()
