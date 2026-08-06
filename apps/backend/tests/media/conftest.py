"""Shared fixtures for `media`'s fast (no-DB) unit + API tests: in-memory fakes for every port
`application/ports.py` declares, mirroring the real adapters' query semantics closely enough to
exercise use-case behaviour without a real database/MinIO/ClamAV. Real-Postgres integration
tests live under `integration/` with their own `conftest.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from media.application.ports import (
    GeneratedVariant,
    MalwareScanResult,
    PresignedUpload,
    ProcessedImage,
)
from media.domain import MediaAsset, ProcessingStatus, ScanStatus
from shared_kernel import EventEnvelope, MediaAssetId


@dataclass
class FakeMediaAssetRepository:
    """Implements `media.application.ports.MediaAssetRepository`."""

    assets: dict[UUID, MediaAsset] = field(default_factory=dict)

    async def get_by_id(self, asset_id: MediaAssetId) -> MediaAsset | None:
        return self.assets.get(asset_id.value)

    async def add(self, asset: MediaAsset) -> None:
        self.assets[asset.id.value] = asset

    async def save(self, asset: MediaAsset) -> None:
        self.assets[asset.id.value] = asset

    async def delete(self, asset_id: MediaAssetId) -> None:
        self.assets.pop(asset_id.value, None)

    async def list_pending_scan(self, *, limit: int) -> list[MediaAsset]:
        items = [a for a in self.assets.values() if a.scan_status is ScanStatus.PENDING]
        return sorted(items, key=lambda a: a.created_at)[:limit]

    async def list_pending_processing(self, *, limit: int) -> list[MediaAsset]:
        items = [
            a
            for a in self.assets.values()
            if a.scan_status is ScanStatus.CLEAN and a.processing_status is ProcessingStatus.PENDING
        ]
        return sorted(items, key=lambda a: a.created_at)[:limit]


@dataclass
class FakeStorage:
    """Implements `media.application.ports.StoragePort` over an in-memory dict of bytes."""

    objects: dict[str, bytes] = field(default_factory=dict)
    presign_calls: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    async def generate_presigned_upload(
        self, *, storage_key: str, content_type: str, expires_in_seconds: int
    ) -> PresignedUpload:
        self.presign_calls.append(storage_key)
        return PresignedUpload(
            upload_url=f"https://minio.local/{storage_key}",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
        )

    async def object_exists(self, storage_key: str) -> bool:
        return storage_key in self.objects

    async def object_size(self, storage_key: str) -> int:
        return len(self.objects[storage_key])

    async def download_object(self, storage_key: str) -> bytes:
        return self.objects[storage_key]

    async def upload_object(self, *, storage_key: str, data: bytes, content_type: str) -> None:
        self.objects[storage_key] = data

    async def delete_object(self, storage_key: str) -> None:
        self.objects.pop(storage_key, None)
        self.deleted.append(storage_key)


class FakeMalwareScanner:
    """Implements `media.application.ports.MalwareScanPort`. Returns whatever
    `next_result` is set to (default CLEAN); `infected_keys` marks specific bytes payloads as
    infected by content equality, for tests that need per-asset control within one batch."""

    def __init__(self, *, next_result: MalwareScanResult = MalwareScanResult.CLEAN) -> None:
        self.next_result = next_result
        self.infected_payloads: set[bytes] = set()
        self.calls: list[bytes] = []

    async def scan(self, *, data: bytes, declared_content_type: str) -> MalwareScanResult:
        self.calls.append(data)
        if data in self.infected_payloads:
            return MalwareScanResult.INFECTED
        return self.next_result


class FakeImageProcessor:
    """Implements `media.application.ports.ImageProcessingPort`. "Processing" is a no-op
    passthrough that reports one THUMBNAIL variant -- these are use-case-level tests, not codec
    tests (Pillow's own adapter is exercised by `test_image_processing.py`)."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def process(self, *, data: bytes, content_type: str) -> ProcessedImage:
        if self.fail:
            raise RuntimeError("simulated processing failure")
        return ProcessedImage(
            stripped_original=data,
            variants=(
                GeneratedVariant(
                    variant_kind="THUMBNAIL", data=b"thumb", width_px=10, height_px=10
                ),
            ),
        )


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


@pytest.fixture
def fake_assets() -> FakeMediaAssetRepository:
    return FakeMediaAssetRepository()


@pytest.fixture
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def fake_scanner() -> FakeMalwareScanner:
    return FakeMalwareScanner()


@pytest.fixture
def fake_processor() -> FakeImageProcessor:
    return FakeImageProcessor()


@pytest.fixture
def fake_outbox() -> FakeOutbox:
    return FakeOutbox()
