"""media/domain -- the MediaAsset aggregate, its ImageVariant child entity, value objects, and
typed exceptions (Task P-06). Imports `shared_kernel` only (Clean Architecture rule 1); never
imported by another module (`domain/` is never part of a module's public surface, AIR-02)."""

from __future__ import annotations

from media.domain.exceptions import (
    AssetNotDeliverableError,
    IllegalAssetStateTransitionError,
    MediaDomainError,
    OversizeMediaError,
    ScanNotCleanError,
    UnsupportedMediaTypeError,
    VariantNotFoundError,
)
from media.domain.image_variant import ImageVariant
from media.domain.media_asset import MediaAsset
from media.domain.value_objects import (
    EXTENSION_BY_CONTENT_TYPE,
    MAX_IMAGE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
    ContentType,
    OwnerContextType,
    ProcessingStatus,
    ScanStatus,
    VariantKind,
    is_video,
    max_size_bytes_for,
)

__all__ = [
    "EXTENSION_BY_CONTENT_TYPE",
    "MAX_IMAGE_SIZE_BYTES",
    "MAX_VIDEO_SIZE_BYTES",
    "AssetNotDeliverableError",
    "ContentType",
    "IllegalAssetStateTransitionError",
    "ImageVariant",
    "MediaAsset",
    "MediaDomainError",
    "OversizeMediaError",
    "OwnerContextType",
    "ProcessingStatus",
    "ScanNotCleanError",
    "ScanStatus",
    "UnsupportedMediaTypeError",
    "VariantKind",
    "VariantNotFoundError",
    "is_video",
    "max_size_bytes_for",
]
