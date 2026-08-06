"""Unit tests for `MediaProcessingUseCases` (the async intake pipeline: scan then process)
against the fake ports in `conftest.py`. Covers I-20's `QuarantinePolicy`, BRULE-12's
exif-stripped-before-any-variant ordering, and `NonBlockingPolicy` (QR-05: one asset's failure
never stops the batch)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from media.application.ports import MalwareScanResult
from media.application.processing_use_cases import MediaProcessingUseCases
from media.domain import MediaAsset, OwnerContextType, ProcessingStatus, ScanStatus
from shared_kernel import MediaAssetId, UserId

from .conftest import (
    FakeImageProcessor,
    FakeMalwareScanner,
    FakeMediaAssetRepository,
    FakeOutbox,
    FakeStorage,
)

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _uploaded_asset(*, repo: FakeMediaAssetRepository, storage: FakeStorage) -> MediaAsset:
    asset = MediaAsset.initiate(
        asset_id=MediaAssetId(value=uuid4()),
        content_type_raw="image/jpeg",
        size_bytes=1024,
        owner_context_type=OwnerContextType.LISTING,
        uploaded_by=UserId(value=uuid4()),
        now=NOW,
    )
    repo.assets[asset.id.value] = asset
    storage.objects[asset.storage_key] = b"fake-image-bytes"
    return asset


@pytest.fixture
def processing_use_cases(
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
    fake_scanner: FakeMalwareScanner,
    fake_processor: FakeImageProcessor,
    fake_outbox: FakeOutbox,
) -> MediaProcessingUseCases:
    return MediaProcessingUseCases(
        assets=fake_assets,
        storage=fake_storage,
        scanner=fake_scanner,
        processor=fake_processor,
        outbox=fake_outbox,
    )


async def test_run_scan_batch_skips_assets_with_no_uploaded_bytes_yet(
    processing_use_cases: MediaProcessingUseCases,
    fake_assets: FakeMediaAssetRepository,
) -> None:
    asset = MediaAsset.initiate(
        asset_id=MediaAssetId(value=uuid4()),
        content_type_raw="image/jpeg",
        size_bytes=1024,
        owner_context_type=OwnerContextType.LISTING,
        uploaded_by=UserId(value=uuid4()),
        now=NOW,
    )
    fake_assets.assets[asset.id.value] = asset  # no bytes ever PUT to storage

    scanned = await processing_use_cases.run_scan_batch(now=NOW)

    assert scanned == 0
    assert fake_assets.assets[asset.id.value].scan_status is ScanStatus.PENDING


async def test_run_scan_batch_marks_clean_asset_scanned_clean(
    processing_use_cases: MediaProcessingUseCases,
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
) -> None:
    asset = _uploaded_asset(repo=fake_assets, storage=fake_storage)

    scanned = await processing_use_cases.run_scan_batch(now=NOW)

    assert scanned == 1
    assert fake_assets.assets[asset.id.value].scan_status is ScanStatus.CLEAN


async def test_I20_run_scan_batch_quarantines_infected_asset_and_publishes_rejected(
    processing_use_cases: MediaProcessingUseCases,
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
    fake_scanner: FakeMalwareScanner,
    fake_outbox: FakeOutbox,
) -> None:
    asset = _uploaded_asset(repo=fake_assets, storage=fake_storage)
    fake_scanner.next_result = MalwareScanResult.INFECTED

    await processing_use_cases.run_scan_batch(now=NOW)

    assert fake_assets.assets[asset.id.value].scan_status is ScanStatus.QUARANTINED
    assert [type(e).__name__ for e in fake_outbox.events] == ["MediaAssetRejected"]


async def test_run_processing_batch_ignores_assets_not_yet_scanned_clean(
    processing_use_cases: MediaProcessingUseCases,
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
) -> None:
    _uploaded_asset(repo=fake_assets, storage=fake_storage)  # still scan_status=PENDING

    processed = await processing_use_cases.run_processing_batch(now=NOW)

    assert processed == 0


async def test_BRULE_12_run_processing_batch_completes_and_sets_exif_stripped_with_variants(
    processing_use_cases: MediaProcessingUseCases,
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
) -> None:
    asset = _uploaded_asset(repo=fake_assets, storage=fake_storage)
    fake_assets.assets[asset.id.value] = asset.mark_scanned_clean(now=NOW)

    processed = await processing_use_cases.run_processing_batch(now=NOW)

    assert processed == 1
    updated = fake_assets.assets[asset.id.value]
    assert updated.processing_status is ProcessingStatus.COMPLETED
    assert updated.exif_stripped is True
    assert len(updated.variants) == 1
    assert updated.is_delivery_available is True


async def test_run_processing_batch_publishes_media_asset_ready(
    processing_use_cases: MediaProcessingUseCases,
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
    fake_outbox: FakeOutbox,
) -> None:
    asset = _uploaded_asset(repo=fake_assets, storage=fake_storage)
    fake_assets.assets[asset.id.value] = asset.mark_scanned_clean(now=NOW)

    await processing_use_cases.run_processing_batch(now=NOW)

    assert [type(e).__name__ for e in fake_outbox.events] == ["MediaAssetReady"]


async def test_NonBlockingPolicy_processing_failure_marks_asset_failed_and_does_not_raise(
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
    fake_scanner: FakeMalwareScanner,
    fake_outbox: FakeOutbox,
) -> None:
    """QR-05: a processing failure never blocks -- the failing asset is marked FAILED and the
    use case returns normally rather than raising out of the batch."""
    failing_processor = FakeImageProcessor(fail=True)
    use_cases = MediaProcessingUseCases(
        assets=fake_assets,
        storage=fake_storage,
        scanner=fake_scanner,
        processor=failing_processor,
        outbox=fake_outbox,
    )
    asset = _uploaded_asset(repo=fake_assets, storage=fake_storage)
    fake_assets.assets[asset.id.value] = asset.mark_scanned_clean(now=NOW)

    processed = await use_cases.run_processing_batch(now=NOW)

    assert processed == 1
    updated = fake_assets.assets[asset.id.value]
    assert updated.processing_status is ProcessingStatus.FAILED
    assert updated.is_delivery_available is False
    assert [type(e).__name__ for e in fake_outbox.events] == ["MediaAssetRejected"]


async def test_NonBlockingPolicy_one_failing_asset_does_not_stop_the_rest_of_the_batch(
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
    fake_scanner: FakeMalwareScanner,
    fake_outbox: FakeOutbox,
) -> None:
    failing_processor = FakeImageProcessor(fail=True)
    use_cases = MediaProcessingUseCases(
        assets=fake_assets,
        storage=fake_storage,
        scanner=fake_scanner,
        processor=failing_processor,
        outbox=fake_outbox,
    )
    failing_asset = _uploaded_asset(repo=fake_assets, storage=fake_storage)
    fake_assets.assets[failing_asset.id.value] = failing_asset.mark_scanned_clean(now=NOW)
    other_asset = _uploaded_asset(repo=fake_assets, storage=fake_storage)
    fake_assets.assets[other_asset.id.value] = other_asset.mark_scanned_clean(now=NOW)

    processed = await use_cases.run_processing_batch(now=NOW)

    assert processed == 2
    assert fake_assets.assets[failing_asset.id.value].processing_status is ProcessingStatus.FAILED
    assert fake_assets.assets[other_asset.id.value].processing_status is ProcessingStatus.FAILED
