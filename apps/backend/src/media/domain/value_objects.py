"""media -- value objects (DDD Sec 5.6 BC-06: `StorageReference`, `ContentType`, `Size`,
`ScanStatus`, `ProcessingStatus`, `OwnerContextRef`, plus `VariantKind` for the `ImageVariant`
child entity). Persistence-ignorant, mirrors `identity.domain.value_objects`'s style.
"""

from __future__ import annotations

from enum import StrEnum

MAX_IMAGE_SIZE_BYTES = int(1.2 * 1024 * 1024)
"""ADR-0008: tightened from the original 10 MB image cap down to 1.2 MB per image (repository
owner's explicit instruction when video support was added, to keep the image path cheap now that
`ImageProcessingPort` re-encodes every original in memory). Also
`contracts/openapi.yaml` `MediaUploadInitRequest.sizeBytes` description, kept in sync by hand."""

MAX_VIDEO_SIZE_BYTES = 30 * 1024 * 1024
"""ADR-0008: the video cap, in the same explicit instruction -- video gets no server-side
transcoding/variant generation (no ffmpeg pipeline exists), so this bounds storage/bandwidth
cost directly rather than a processing cost."""


class ContentType(StrEnum):
    """DDD Sec 5.6 VO `ContentType`. Originally "image whitelist only" (BRULE-11, DEC-10);
    ADR-0008 widens it to also admit two video formats. Exactly the values
    `contracts/openapi.yaml`'s `MediaAsset.contentType`/`MediaUploadInitRequest.contentType` enum
    lists; not a general MIME-type VO."""

    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"
    MP4 = "video/mp4"
    WEBM = "video/webm"


_VIDEO_CONTENT_TYPES = frozenset({ContentType.MP4, ContentType.WEBM})


def is_video(content_type: ContentType) -> bool:
    return content_type in _VIDEO_CONTENT_TYPES


def max_size_bytes_for(content_type: ContentType) -> int:
    return MAX_VIDEO_SIZE_BYTES if is_video(content_type) else MAX_IMAGE_SIZE_BYTES


class OwnerContextType(StrEnum):
    """DDD Sec 5.6 VO `OwnerContextRef` (listing / profile / banner creative). Frozen enum,
    verbatim from `contracts/openapi.yaml`'s `MediaAsset.ownerContextType`."""

    LISTING = "LISTING"
    PROFILE_PORTFOLIO = "PROFILE_PORTFOLIO"
    VERIFICATION_DOCUMENT = "VERIFICATION_DOCUMENT"
    BANNER_CREATIVE = "BANNER_CREATIVE"


class ScanStatus(StrEnum):
    """DDD Sec 5.6 VO `ScanStatus` (Pending/Clean/Quarantined -- FR-MEDIA-004). Single-shot: the
    only legal transition out of PENDING is to CLEAN or QUARANTINED; both are terminal (no
    re-scan in v1)."""

    PENDING = "PENDING"
    CLEAN = "CLEAN"
    QUARANTINED = "QUARANTINED"


class ProcessingStatus(StrEnum):
    """DDD Sec 5.6 VO `ProcessingStatus`. PENDING until scanning is CLEAN and the
    `ImageProcessingService` (EXIF strip + variant generation) has run; COMPLETED/FAILED are
    terminal. Stays PENDING forever for a QUARANTINED asset -- processing is never attempted for
    an asset the `QuarantinePolicy` has already excluded from delivery."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VariantKind(StrEnum):
    """DDD Sec 5.6 "set of ImageVariant (thumbnail/optimised -- FR-MEDIA-005)". Frozen enum,
    verbatim from `contracts/openapi.yaml`'s `MediaAssetVariants.kind`."""

    THUMBNAIL = "THUMBNAIL"
    OPTIMIZED = "OPTIMIZED"


EXTENSION_BY_CONTENT_TYPE: dict[ContentType, str] = {
    ContentType.JPEG: ".jpg",
    ContentType.PNG: ".png",
    ContentType.WEBP: ".webp",
    ContentType.MP4: ".mp4",
    ContentType.WEBM: ".webm",
}
"""Shared by `media_asset.py` (original storage key) and `application/processing_use_cases.py`
(variant storage keys) -- one place naming the on-disk extension per whitelisted content type."""
