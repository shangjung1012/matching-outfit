from io import BytesIO
import uuid

import httpx

from app.core.config import settings


class Human3DError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class Human3DClient:
    def __init__(self) -> None:
        tryon_base_url = settings.tryon_api_url.rstrip("/")
        self.base_url = f"{tryon_base_url}/human3d" if tryon_base_url else ""

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": settings.tryon_api_key}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.base_url or not settings.tryon_api_key:
            raise Human3DError("TryOn API 尚未設定")
        timeout = kwargs.pop(
            "timeout",
            httpx.Timeout(settings.human3d_request_timeout_seconds, connect=10.0),
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
            raise Human3DError(
                f"Human3D 回傳 {error.response.status_code}: {detail}",
                status_code=error.response.status_code,
            ) from error
        except httpx.HTTPError as error:
            raise Human3DError(f"Human3D 請求失敗：{error}") from error

    def health(self) -> tuple[bool, str | None]:
        try:
            payload = self._request("GET", "/health", timeout=10.0).json()
        except (Human3DError, ValueError) as error:
            return False, str(error)
        if payload.get("ok") is not True:
            return False, str(payload.get("error") or "LHM++ 模型尚未就緒")
        return True, None

    def create_job(self, image_content: bytes, image_content_type: str) -> dict:
        response = self._request(
            "POST",
            "/v1/jobs",
            files={
                "image": (
                    "try-on-result.png",
                    BytesIO(image_content),
                    image_content_type,
                )
            },
        )
        try:
            return response.json()
        except ValueError as error:
            raise Human3DError("Human3D 建立工作時回傳無效資料") from error

    def get_job(self, remote_job_id: uuid.UUID) -> dict:
        try:
            return self._request("GET", f"/v1/jobs/{remote_job_id}").json()
        except ValueError as error:
            raise Human3DError("Human3D 工作狀態格式無效") from error

    def get_result(self, remote_job_id: uuid.UUID) -> tuple[bytes, str]:
        response = self._request("GET", f"/v1/jobs/{remote_job_id}/result")
        artifact_format = response.headers.get("x-artifact-format", "ply")
        if artifact_format != "ply":
            raise Human3DError(f"Human3D 回傳不支援的格式：{artifact_format}")
        return response.content, artifact_format

    def delete_job(self, remote_job_id: uuid.UUID) -> None:
        self._request("DELETE", f"/v1/jobs/{remote_job_id}")


human3d_client = Human3DClient()
