"""Unit tests for `MediaIntakeUseCases` (initMediaUpload/getMedia/deleteMedia) against the fake
ports in `conftest.py`."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from media.application.exceptions import MediaAssetNotFoundError, NotAssetOwnerError
from media.application.intake_use_cases import MediaIntakeUseCases
from media.domain import ScanStatus, UnsupportedMediaTypeError
from shared_kernel import MediaAssetId, UserId

from .conftest import FakeMediaAssetRepository, FakeOutbox, FakeStorage

NOW = datetime(2026, 7, 11, tzinfo=UTC)


@pytest.fixture
def intake_use_cases(
    fake_assets: FakeMediaAssetRepository, fake_storage: FakeStorage, fake_outbox: FakeOutbox
) -> MediaIntakeUseCases:
    return MediaIntakeUseCases(
        assets=fake_assets, storage=fake_storage, outbox=fake_outbox, presign_expiry_seconds=900
    )


async def test_init_media_upload_persists_asset_and_returns_presigned_url(
    intake_use_cases: MediaIntakeUseCases,
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
) -> None:
    uploader = UserId(value=uuid4())
    asset, presigned = await intake_use_cases.init_media_upload(
        content_type="image/jpeg",
        size_bytes=2048,
        owner_context_type="LISTING",
        uploaded_by=uploader,
        now=NOW,
    )
    assert asset.id.value in fake_assets.assets
    assert asset.scan_status is ScanStatus.PENDING
    assert asset.uploaded_by == uploader
    assert presigned.method == "PUT"
    assert asset.storage_key in fake_storage.presign_calls


async def test_init_media_upload_publishes_media_asset_accepted(
    intake_use_cases: MediaIntakeUseCases, fake_outbox: FakeOutbox
) -> None:
    await intake_use_cases.init_media_upload(
        content_type="image/png",
        size_bytes=512,
        owner_context_type="PROFILE_PORTFOLIO",
        uploaded_by=UserId(value=uuid4()),
        now=NOW,
    )
    assert [type(e).__name__ for e in fake_outbox.events] == ["MediaAssetAccepted"]


async def test_init_media_upload_rejects_non_image_before_persisting_or_presigning(
    intake_use_cases: MediaIntakeUseCases,
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
) -> None:
    """ADR-0008 widened the whitelist to admit `video/mp4`/`video/webm` -- `application/pdf`
    is still outside it, so it's the rejected example now."""
    with pytest.raises(UnsupportedMediaTypeError):
        await intake_use_cases.init_media_upload(
            content_type="application/pdf",
            size_bytes=512,
            owner_context_type="LISTING",
            uploaded_by=UserId(value=uuid4()),
            now=NOW,
        )
    assert fake_assets.assets == {}
    assert fake_storage.presign_calls == []


async def test_get_media_returns_the_persisted_asset(
    intake_use_cases: MediaIntakeUseCases,
) -> None:
    asset, _ = await intake_use_cases.init_media_upload(
        content_type="image/jpeg",
        size_bytes=100,
        owner_context_type="LISTING",
        uploaded_by=UserId(value=uuid4()),
        now=NOW,
    )
    fetched = await intake_use_cases.get_media(asset.id)
    assert fetched.id == asset.id


async def test_get_media_raises_for_unknown_id(intake_use_cases: MediaIntakeUseCases) -> None:
    with pytest.raises(MediaAssetNotFoundError):
        await intake_use_cases.get_media(MediaAssetId(value=uuid4()))


async def test_delete_media_by_owner_removes_asset_and_its_objects(
    intake_use_cases: MediaIntakeUseCases,
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
) -> None:
    uploader = UserId(value=uuid4())
    asset, _ = await intake_use_cases.init_media_upload(
        content_type="image/jpeg",
        size_bytes=100,
        owner_context_type="LISTING",
        uploaded_by=uploader,
        now=NOW,
    )
    fake_storage.objects[asset.storage_key] = b"bytes"

    await intake_use_cases.delete_media(asset.id, requested_by=uploader)

    assert asset.id.value not in fake_assets.assets
    assert asset.storage_key in fake_storage.deleted


async def test_delete_media_by_non_owner_raises_and_deletes_nothing(
    intake_use_cases: MediaIntakeUseCases,
    fake_assets: FakeMediaAssetRepository,
    fake_storage: FakeStorage,
) -> None:
    asset, _ = await intake_use_cases.init_media_upload(
        content_type="image/jpeg",
        size_bytes=100,
        owner_context_type="LISTING",
        uploaded_by=UserId(value=uuid4()),
        now=NOW,
    )
    other = UserId(value=uuid4())

    with pytest.raises(NotAssetOwnerError):
        await intake_use_cases.delete_media(asset.id, requested_by=other)

    assert asset.id.value in fake_assets.assets
    assert fake_storage.deleted == []


async def test_delete_media_raises_for_unknown_id(intake_use_cases: MediaIntakeUseCases) -> None:
    with pytest.raises(MediaAssetNotFoundError):
        await intake_use_cases.delete_media(
            MediaAssetId(value=uuid4()), requested_by=UserId(value=uuid4())
        )
