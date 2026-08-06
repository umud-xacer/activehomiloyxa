"""Unit tests for the `MediaAsset` aggregate (DDD Sec 5.6): the intake factory's
`ImageOnlyPolicy`/size cap, the scan/processing state machine, and I-20's `QuarantinePolicy` --
"a stored MediaAsset is image-typed, malware-clean, and EXIF/GPS-free; quarantined assets are
never delivered"."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from media.domain import (
    MAX_IMAGE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
    AssetNotDeliverableError,
    ContentType,
    IllegalAssetStateTransitionError,
    ImageVariant,
    MediaAsset,
    OversizeMediaError,
    OwnerContextType,
    ProcessingStatus,
    ScanNotCleanError,
    ScanStatus,
    UnsupportedMediaTypeError,
    VariantKind,
    VariantNotFoundError,
)
from shared_kernel import MediaAssetId, UserId

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _new_asset(*, content_type: str = "image/jpeg", size_bytes: int = 1024) -> MediaAsset:
    return MediaAsset.initiate(
        asset_id=MediaAssetId(value=uuid4()),
        content_type_raw=content_type,
        size_bytes=size_bytes,
        owner_context_type=OwnerContextType.LISTING,
        uploaded_by=UserId(value=uuid4()),
        now=NOW,
    )


def _variant(kind: VariantKind = VariantKind.THUMBNAIL) -> ImageVariant:
    return ImageVariant(
        id=uuid4(),
        variant_kind=kind,
        storage_key=f"media/x/{kind.value.lower()}.jpg",
        width_px=200,
        height_px=200,
        size_bytes=10,
        created_at=NOW,
    )


# --- initiate: ImageOnlyPolicy + size cap (FR-MEDIA-001/002) ----------------------------------


def test_initiate_accepts_every_whitelisted_content_type() -> None:
    for content_type in ("image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"):
        asset = _new_asset(content_type=content_type, size_bytes=1024)
        assert asset.content_type is ContentType(content_type)
        assert asset.scan_status is ScanStatus.PENDING
        assert asset.processing_status is ProcessingStatus.PENDING
        assert asset.exif_stripped is False
        assert asset.owner_context_id is None


def test_initiate_rejects_non_image_content_type() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        _new_asset(content_type="application/pdf")


def test_initiate_rejects_oversize_upload() -> None:
    with pytest.raises(OversizeMediaError):
        _new_asset(size_bytes=MAX_IMAGE_SIZE_BYTES + 1)


def test_initiate_accepts_exactly_the_size_cap() -> None:
    asset = _new_asset(size_bytes=MAX_IMAGE_SIZE_BYTES)
    assert asset.size_bytes == MAX_IMAGE_SIZE_BYTES


# --- ADR-0008: video gets its own, larger size cap ---------------------------------------------


def test_initiate_rejects_oversize_video_upload() -> None:
    with pytest.raises(OversizeMediaError):
        _new_asset(content_type="video/mp4", size_bytes=MAX_VIDEO_SIZE_BYTES + 1)


def test_initiate_accepts_exactly_the_video_size_cap() -> None:
    asset = _new_asset(content_type="video/mp4", size_bytes=MAX_VIDEO_SIZE_BYTES)
    assert asset.size_bytes == MAX_VIDEO_SIZE_BYTES


def test_initiate_rejects_video_sized_image_as_oversize() -> None:
    """A payload under the video cap but over the (much smaller) image cap must still be
    rejected when declared as an image -- the cap is chosen by the declared content type, not a
    single flat ceiling."""
    with pytest.raises(OversizeMediaError):
        _new_asset(content_type="image/jpeg", size_bytes=MAX_IMAGE_SIZE_BYTES + 1)


def test_initiate_rejects_zero_or_negative_size() -> None:
    with pytest.raises(OversizeMediaError):
        _new_asset(size_bytes=0)


def test_initiate_derives_storage_key_from_the_assets_own_public_id() -> None:
    asset_id = MediaAssetId(value=uuid4())
    asset = MediaAsset.initiate(
        asset_id=asset_id,
        content_type_raw="image/png",
        size_bytes=100,
        owner_context_type=OwnerContextType.LISTING,
        uploaded_by=UserId(value=uuid4()),
        now=NOW,
    )
    assert asset.storage_key == f"media/{asset_id.value}/original.png"


# --- scanning (FR-MEDIA-004) --------------------------------------------------------------------


def test_mark_scanned_clean_transitions_pending_to_clean() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW)
    assert asset.scan_status is ScanStatus.CLEAN


def test_mark_scanned_clean_twice_raises() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW)
    with pytest.raises(IllegalAssetStateTransitionError):
        asset.mark_scanned_clean(now=NOW)


def test_quarantine_transitions_pending_to_quarantined() -> None:
    asset = _new_asset().quarantine(now=NOW)
    assert asset.scan_status is ScanStatus.QUARANTINED


def test_quarantine_after_clean_raises() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW)
    with pytest.raises(IllegalAssetStateTransitionError):
        asset.quarantine(now=NOW)


# --- processing (FR-MEDIA-003/005, BRULE-12) ----------------------------------------------------


def test_complete_processing_requires_clean_scan() -> None:
    asset = _new_asset()
    with pytest.raises(ScanNotCleanError):
        asset.complete_processing(variants=(_variant(),), now=NOW)


def test_complete_processing_sets_exif_stripped_and_variants_together() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW)
    variant = _variant()
    processed = asset.complete_processing(variants=(variant,), now=NOW)
    assert processed.exif_stripped is True
    assert processed.processing_status is ProcessingStatus.COMPLETED
    assert processed.variants == (variant,)


def test_fail_processing_requires_clean_scan() -> None:
    asset = _new_asset()
    with pytest.raises(ScanNotCleanError):
        asset.fail_processing(now=NOW)


def test_fail_processing_transitions_pending_to_failed() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW)
    failed = asset.fail_processing(now=NOW)
    assert failed.processing_status is ProcessingStatus.FAILED
    assert failed.exif_stripped is False
    assert failed.variants == ()


def test_complete_processing_twice_raises() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW)
    processed = asset.complete_processing(variants=(_variant(),), now=NOW)
    with pytest.raises(IllegalAssetStateTransitionError):
        processed.complete_processing(variants=(_variant(),), now=NOW)


def test_variant_returns_matching_kind() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW)
    thumb = _variant(VariantKind.THUMBNAIL)
    processed = asset.complete_processing(variants=(thumb,), now=NOW)
    assert processed.variant(VariantKind.THUMBNAIL) is thumb


def test_variant_raises_for_missing_kind() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW)
    processed = asset.complete_processing(variants=(_variant(VariantKind.THUMBNAIL),), now=NOW)
    with pytest.raises(VariantNotFoundError):
        processed.variant(VariantKind.OPTIMIZED)


# --- I-20 QuarantinePolicy: delivery gate --------------------------------------------------------


def test_I20_freshly_initiated_asset_is_not_delivery_available() -> None:
    asset = _new_asset()
    assert asset.is_delivery_available is False
    with pytest.raises(AssetNotDeliverableError):
        asset.require_delivery_available()


def test_I20_clean_scan_alone_is_not_delivery_available() -> None:
    """The safer reading of `contracts/openapi.yaml`'s `MediaAsset.url` docstring: the original
    is not delivery-available on scan_status=CLEAN alone, only once processing (EXIF/GPS strip)
    has also completed -- see `MediaAsset.is_delivery_available`'s own docstring."""
    asset = _new_asset().mark_scanned_clean(now=NOW)
    assert asset.is_delivery_available is False


def test_I20_quarantined_asset_is_never_delivery_available() -> None:
    asset = _new_asset().quarantine(now=NOW)
    assert asset.is_delivery_available is False
    with pytest.raises(AssetNotDeliverableError):
        asset.require_delivery_available()


def test_I20_failed_processing_is_never_delivery_available() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW).fail_processing(now=NOW)
    assert asset.is_delivery_available is False


def test_I20_clean_and_completed_is_delivery_available() -> None:
    asset = _new_asset().mark_scanned_clean(now=NOW)
    processed = asset.complete_processing(variants=(_variant(),), now=NOW)
    assert processed.is_delivery_available is True
    processed.require_delivery_available()  # does not raise
