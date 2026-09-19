from __future__ import annotations

from io import BytesIO
import os
from typing import Protocol
import uuid

from minio import Minio
from minio.error import S3Error

from job_models import JobManifest


class JobStorage(Protocol):
    def ensure_bucket(self) -> None: ...
    def put(self, object_key: str, content: bytes, content_type: str) -> None: ...
    def get(self, object_key: str) -> bytes: ...
    def delete(self, object_key: str | None) -> None: ...
    def save_manifest(self, manifest: JobManifest) -> None: ...
    def get_manifest(self, job_id: uuid.UUID) -> JobManifest | None: ...
    def list_manifests(self) -> list[JobManifest]: ...
    def delete_job(self, job_id: uuid.UUID) -> None: ...


class MinioJobStorage:
    def __init__(self) -> None:
        self.bucket = os.getenv("MINIO_BUCKET", "human3d")
        self.client = Minio(
            os.getenv("MINIO_ENDPOINT", "minio:9000"),
            access_key=os.environ["MINIO_ACCESS_KEY"],
            secret_key=os.environ["MINIO_SECRET_KEY"],
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )

    @staticmethod
    def manifest_key(job_id: uuid.UUID) -> str:
        return f"jobs/{job_id}/metadata.json"

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(
            self.bucket,
            object_key,
            BytesIO(content),
            len(content),
            content_type=content_type,
        )

    def get(self, object_key: str) -> bytes:
        response = self.client.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, object_key: str | None) -> None:
        if object_key:
            self.client.remove_object(self.bucket, object_key)

    def save_manifest(self, manifest: JobManifest) -> None:
        self.put(
            self.manifest_key(manifest.id),
            manifest.model_dump_json().encode(),
            "application/json",
        )

    def get_manifest(self, job_id: uuid.UUID) -> JobManifest | None:
        try:
            return JobManifest.model_validate_json(self.get(self.manifest_key(job_id)))
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject"}:
                return None
            raise

    def list_manifests(self) -> list[JobManifest]:
        manifests: list[JobManifest] = []
        for item in self.client.list_objects(self.bucket, prefix="jobs/", recursive=True):
            if item.object_name and item.object_name.endswith("/metadata.json"):
                try:
                    manifests.append(
                        JobManifest.model_validate_json(self.get(item.object_name))
                    )
                except (S3Error, ValueError):
                    continue
        return manifests

    def delete_job(self, job_id: uuid.UUID) -> None:
        keys = [
            item.object_name
            for item in self.client.list_objects(
                self.bucket, prefix=f"jobs/{job_id}/", recursive=True
            )
            if item.object_name
        ]
        manifest_key = self.manifest_key(job_id)
        for key in keys:
            if key != manifest_key:
                self.delete(key)
        if manifest_key in keys:
            self.delete(manifest_key)
