"""media -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
operations tagged to this module (contracts/openapi.yaml). Schema only: no aggregate
type is exposed here, no business behaviour, no validation beyond what Pydantic
itself does structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from active_home_shared import CamelModel


class MediaAsset(CamelModel):
    """Image/video asset metadata (BC-06). Bytes live in MinIO/CDN. Images and video only
    (DEC-10, widened by ADR-0008 to admit two video formats)."""

    id: UUID
    owner_context_type: (
        Literal["LISTING", "PROFILE_PORTFOLIO", "VERIFICATION_DOCUMENT", "BANNER_CREATIVE"] | None
    ) = None
    owner_context_id: UUID | None = None
    content_type: Literal[
        "image/jpeg", "image/png", "image/webp", "image/gif", "video/mp4", "video/webm"
    ]
    """Image/video whitelist; anything else is rejected at intake."""
    size_bytes: int | None = None
    scan_status: Literal["PENDING", "CLEAN", "QUARANTINED"]
    processing_status: Literal["PENDING", "COMPLETED", "FAILED"]
    url: str | None = None
    """CDN delivery URL for the original (only when CLEAN)."""
    variants: list[MediaAssetVariants] | None = None
    duration_seconds: float | None = None
    """Additive: only ever set for `video/mp4`/`video/webm` content, once processing has probed
    the container's own declared duration (promo-video business rule support, `profiles`
    module) -- always `None` for images/GIF."""
    created_at: datetime


class MediaAssetVariants(CamelModel):
    """OpenAPI `MediaAssetVariants`."""

    kind: Literal["THUMBNAIL", "OPTIMIZED"] | None = None
    url: str | None = None
    width: int | None = None
    height: int | None = None


class MediaUploadInitRequest(CamelModel):
    """Request a presigned direct-upload target. Images and video only."""

    content_type: Literal[
        "image/jpeg", "image/png", "image/webp", "image/gif", "video/mp4", "video/webm"
    ]
    size_bytes: int
    """Max 1.2 MB per image, max 30 MB per video (ADR-0008)."""
    owner_context_type: Literal[
        "LISTING", "PROFILE_PORTFOLIO", "VERIFICATION_DOCUMENT", "BANNER_CREATIVE"
    ]


class MediaUploadInitResponse(CamelModel):
    """OpenAPI `MediaUploadInitResponse`."""

    media_asset_id: UUID
    upload_url: str
    """Presigned MinIO URL; client PUTs the bytes directly."""
    method: Literal["PUT"]
    headers: dict[str, Any] | None = None
    expires_at: datetime
