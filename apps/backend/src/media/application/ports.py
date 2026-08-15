"""media/application -- ports (Task P-06). Abstract surface only (typing.Protocol);
`infrastructure/` implements every one of these, never the reverse (Clean Architecture rule 4).
`MalwareScanPort`/`StoragePort` are the two ports DDD Sec 5.6 names explicitly under BC-06's
domain services; provider SDK types (boto3/MinIO, the malware scanner's wire protocol) never
appear here -- only plain domain/primitive types (`provider-sdk-confined-to-infrastructure`,
tools/importlinter.cfg).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from media.domain import MediaAsset
from shared_kernel import MediaAssetId


class MediaAssetRepository(Protocol):
    """One repository per aggregate (`MediaAsset`, including its `ImageVariant` child entities --
    Clean Architecture rule 2)."""

    async def get_by_id(self, asset_id: MediaAssetId) -> MediaAsset | None: ...

    async def add(self, asset: MediaAsset) -> None: ...

    async def save(self, asset: MediaAsset) -> None: ...

    async def delete(self, asset_id: MediaAssetId) -> None: ...

    async def list_pending_scan(self, *, limit: int) -> list[MediaAsset]:
        """`scan_status == PENDING`, oldest first. The worker still has to confirm the bytes have
        actually landed in storage (`StoragePort.object_exists`) before scanning -- a row can be
        PENDING for a while simply because the client has not PUT yet."""
        ...

    async def list_pending_processing(self, *, limit: int) -> list[MediaAsset]:
        """`scan_status == CLEAN AND processing_status == PENDING`, oldest first."""
        ...


@dataclass(frozen=True)
class PresignedUpload:
    """Result of `StoragePort.generate_presigned_upload`; maps directly onto
    `MediaUploadInitResponse` (`interfaces/dto.py`) without exposing the underlying storage
    key."""

    upload_url: str
    method: Literal["PUT"]
    headers: dict[str, str] | None
    expires_at: datetime


class StoragePort(Protocol):
    """DDD Sec 5.6 `StoragePort`. MinIO behind this in `infrastructure/` (Security Sec 7:
    "presigned, scoped, expiring upload/download URLs ... storage keys are opaque external
    references never exposed as identity")."""

    async def generate_presigned_upload(
        self, *, storage_key: str, content_type: str, expires_in_seconds: int
    ) -> PresignedUpload: ...

    async def object_exists(self, storage_key: str) -> bool: ...

    async def object_size(self, storage_key: str) -> int:
        """Actual uploaded size, re-verified against the declared `size_bytes` before scanning
        (Security Sec 7 D-4: size caps enforced "at intake and by the presigned policy" --
        `object_size` is the second half of that defence-in-depth, since a presigned PUT URL
        alone cannot bound the client's upload)."""
        ...

    async def download_object(self, storage_key: str) -> bytes: ...

    async def upload_object(self, *, storage_key: str, data: bytes, content_type: str) -> None: ...

    async def delete_object(self, storage_key: str) -> None: ...


class MalwareScanResult(StrEnum):
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"


class MalwareScanPort(Protocol):
    """DDD Sec 5.6 `MalwareScanPort` (FR-MEDIA-004). Also the intake-validation boundary for
    magic-byte/content-sniffing verification (Security Sec 7 T-6: "type + MIME + magic-byte
    verification; malware scan ... quarantine on failure") -- the frozen `ScanStatus` vocabulary
    has no separate value for a type mismatch, so a magic-byte mismatch is reported as
    `INFECTED` too (both converge on `MediaAsset.quarantine`, see its docstring)."""

    async def scan(self, *, data: bytes, declared_content_type: str) -> MalwareScanResult: ...


@dataclass(frozen=True)
class GeneratedVariant:
    """One resized/re-encoded image, ready to be uploaded and recorded as an `ImageVariant`."""

    variant_kind: Literal["THUMBNAIL", "OPTIMIZED"]
    data: bytes
    width_px: int
    height_px: int


@dataclass(frozen=True)
class ProcessedImage:
    """`ImageProcessingService`'s output: the EXIF/GPS-stripped, re-encoded original plus its
    derived variants (BRULE-12: stripping happens before *any* variant is stored, so the
    stripped original and the variants are produced together)."""

    stripped_original: bytes
    variants: tuple[GeneratedVariant, ...]
    duration_seconds: float | None = None
    """Additive (promo-video business rule support): populated only for `video/mp4`/`video/webm`
    content, by reading the container's own declared duration (`infrastructure.video_probe`) --
    `None` for every image/GIF content type (unchanged from before this field existed), and also
    `None` for a video whose duration this dependency-free parser could not confidently read."""


class ImageProcessingPort(Protocol):
    """DDD Sec 5.6 `ImageProcessingService` (async variants). Re-decodes/re-encodes to strip
    active content and EXIF/GPS metadata (Security Sec 7, BRULE-12, closing the
    location-disclosure vector I-2) and produces the THUMBNAIL/OPTIMIZED variants
    (FR-MEDIA-005)."""

    async def process(self, *, data: bytes, content_type: str) -> ProcessedImage: ...
