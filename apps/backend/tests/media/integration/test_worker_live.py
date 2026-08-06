"""Integration test: `MediaIntakeWorker` against a real Postgres `session_factory` (one fresh
session per batch, see `worker.py`'s own docstring) with fake storage/scanner/processor ports --
proves the worker's own session-per-batch transaction wiring, not the adapters behind those
three ports (those are exercised by `test_malware_scan.py`/`test_image_processing.py` and would
need live MinIO/ClamAV, out of this task's CI-without-those-services scope)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from media.domain import MediaAsset, OwnerContextType, ProcessingStatus, ScanStatus
from media.infrastructure.persistence.models import OutboxEventRow
from media.infrastructure.persistence.repository import SqlalchemyMediaAssetRepository
from media.infrastructure.worker import MediaIntakeWorker
from shared_kernel import MediaAssetId, UserId

from ..conftest import FakeImageProcessor, FakeMalwareScanner, FakeStorage

NOW = datetime(2026, 7, 11, tzinfo=UTC)


async def test_run_once_advances_an_asset_through_scan_and_processing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    asset = MediaAsset.initiate(
        asset_id=MediaAssetId(value=uuid4()),
        content_type_raw="image/jpeg",
        size_bytes=1024,
        owner_context_type=OwnerContextType.LISTING,
        uploaded_by=UserId(value=uuid4()),
        now=NOW,
    )
    async with session_factory() as setup_session:
        repo = SqlalchemyMediaAssetRepository(setup_session)
        await repo.add(asset)
        await setup_session.commit()

    storage = FakeStorage(objects={asset.storage_key: b"fake-bytes"})
    worker = MediaIntakeWorker(
        session_factory=session_factory,
        outbox_model=OutboxEventRow,
        storage=storage,
        scanner=FakeMalwareScanner(),
        processor=FakeImageProcessor(),
    )

    # `run_once()` runs a scan batch and a processing batch in the same transaction (worker.py's
    # own docstring: "one scan batch, then one processing batch, in a single fresh transaction"),
    # so a freshly initiated asset clears scan *and* becomes processing-eligible within this one
    # call -- it advances by 2, not split 1-then-1 across two calls.
    first_run_advanced = await worker.run_once()
    assert first_run_advanced == 2
    second_run_advanced = await worker.run_once()
    assert second_run_advanced == 0

    async with session_factory() as check_session:
        fetched = await SqlalchemyMediaAssetRepository(check_session).get_by_id(asset.id)
        assert fetched is not None
        assert fetched.scan_status is ScanStatus.CLEAN
        assert fetched.processing_status is ProcessingStatus.COMPLETED
        assert fetched.is_delivery_available is True


async def test_run_once_returns_zero_when_nothing_is_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    worker = MediaIntakeWorker(
        session_factory=session_factory,
        outbox_model=OutboxEventRow,
        storage=FakeStorage(),
        scanner=FakeMalwareScanner(),
        processor=FakeImageProcessor(),
    )
    assert await worker.run_once() == 0
