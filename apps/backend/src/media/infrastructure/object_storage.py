"""MinIO object-storage adapter (Infra Sec 3: "MinIO -- Object storage, images + derived
variants, presigned uploads"). Implements `media.application.ports.StoragePort`. boto3's S3
client is the only place a MinIO/boto3 SDK type appears (`provider-sdk-confined-to-
infrastructure`, tools/importlinter.cfg) -- everything crossing the port boundary is a plain
`str`/`bytes`/`PresignedUpload`. boto3 is sync, so every network call runs off the event loop via
`asyncio.to_thread` (Playbook Sec 6: "I/O ... MUST be non-blocking"); `generate_presigned_url`
itself makes no network call (pure local HMAC signing), so it runs inline.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from backbone.persistence.env import required_env
from media.application.ports import PresignedUpload


def _minio_use_tls() -> bool:
    return required_env("MINIO_USE_TLS").strip().lower() == "true"


class MinioStorageAdapter:
    def __init__(self, *, client: Any | None = None, bucket: str | None = None) -> None:
        endpoint = required_env("MINIO_ENDPOINT")
        scheme = "https" if _minio_use_tls() else "http"
        self._bucket = bucket or required_env("MINIO_MEDIA_BUCKET")
        self._client = client or boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{endpoint}",
            aws_access_key_id=required_env("MINIO_ROOT_USER"),
            aws_secret_access_key=required_env("MINIO_ROOT_PASSWORD"),
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        # `MINIO_ENDPOINT` (127.0.0.1:9000 in production) is correct for every server-side call
        # in this class -- but a presigned PUT url is handed to a *browser*, which cannot reach
        # the server's own loopback address. `MINIO_PUBLIC_ENDPOINT_URL` is a full base URL
        # (scheme included, e.g. https://activehome.uz/media-upload -- an nginx passthrough
        # proxying straight to MinIO, mirroring MEDIA_CDN_BASE_URL's own "public URL for
        # something MinIO-backed" role for downloads) reachable from outside. Real bug found live:
        # every upload from an actual external browser was silently failing in production (only
        # server-seeded demo data, uploaded from inside the server's own network, ever worked) --
        # this was never caught locally because 127.0.0.1 legitimately IS reachable from a
        # developer's own browser when MinIO also runs on their own machine.
        self._presign_client = client or boto3.client(
            "s3",
            endpoint_url=required_env("MINIO_PUBLIC_ENDPOINT_URL"),
            aws_access_key_id=required_env("MINIO_ROOT_USER"),
            aws_secret_access_key=required_env("MINIO_ROOT_PASSWORD"),
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self._ensured_bucket = False

    async def generate_presigned_upload(
        self, *, storage_key: str, content_type: str, expires_in_seconds: int
    ) -> PresignedUpload:
        await self._ensure_bucket()
        url = self._presign_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": storage_key, "ContentType": content_type},
            ExpiresIn=expires_in_seconds,
        )
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        return PresignedUpload(
            upload_url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            expires_at=expires_at,
        )

    async def object_exists(self, storage_key: str) -> bool:
        await self._ensure_bucket()
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=storage_key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise

    async def object_size(self, storage_key: str) -> int:
        await self._ensure_bucket()
        response = await asyncio.to_thread(
            self._client.head_object, Bucket=self._bucket, Key=storage_key
        )
        size: int = response["ContentLength"]
        return size

    async def download_object(self, storage_key: str) -> bytes:
        await self._ensure_bucket()
        response = await asyncio.to_thread(
            self._client.get_object, Bucket=self._bucket, Key=storage_key
        )
        data: bytes = await asyncio.to_thread(response["Body"].read)
        return data

    async def upload_object(self, *, storage_key: str, data: bytes, content_type: str) -> None:
        await self._ensure_bucket()
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=storage_key,
            Body=data,
            ContentType=content_type,
        )

    async def delete_object(self, storage_key: str) -> None:
        await self._ensure_bucket()
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=storage_key)

    async def _ensure_bucket(self) -> None:
        """Idempotent, self-hosted-MinIO convenience: Task P-00 provisioned the MinIO container
        but not a media bucket inside it (no code needed one yet). Checked once per adapter
        instance, not per call."""
        if self._ensured_bucket:
            return
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
        except ClientError:
            await asyncio.to_thread(self._client.create_bucket, Bucket=self._bucket)
        self._ensured_bucket = True
