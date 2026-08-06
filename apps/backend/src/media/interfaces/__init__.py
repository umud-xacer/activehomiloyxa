"""media.interfaces -- the module's only importable public surface (AIR-02)."""

from __future__ import annotations

from media.interfaces.dto import (
    MediaAsset,
    MediaAssetVariants,
    MediaUploadInitRequest,
    MediaUploadInitResponse,
)
from media.interfaces.ports import (
    MediaIntakePort,
)

__all__ = [
    "MediaAsset",
    "MediaAssetVariants",
    "MediaIntakePort",
    "MediaUploadInitRequest",
    "MediaUploadInitResponse",
]
