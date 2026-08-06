"""media -- typed domain exceptions, one per invariant violated (Playbook Sec 6). Mirrors
`identity.domain.exceptions`'s style. `interfaces/errors.py` maps each of these to a
`contracts.errors.Problem` (closed `ErrorCode` vocabulary).
"""

from __future__ import annotations


class MediaDomainError(Exception):
    """Base for every typed exception raised by media's domain/ layer."""


# --- intake validation (I-20, ImageOnlyPolicy / size policy) ---------------------------------


class UnsupportedMediaTypeError(MediaDomainError):
    """FR-MEDIA-002 `ImageOnlyPolicy`: the declared content type is not in the image whitelist
    (`image/jpeg|png|webp`, BRULE-11). Maps to 422 `UNSUPPORTED_MEDIA_TYPE`."""

    def __init__(self, content_type: str) -> None:
        self.content_type = content_type
        super().__init__(f"content type {content_type!r} is not an accepted image type")


class OversizeMediaError(MediaDomainError):
    """Security Sec 7: declared `size_bytes` exceeds the 10 MB cap. Maps to the same 422
    `UNSUPPORTED_MEDIA_TYPE` as `UnsupportedMediaTypeError` -- `contracts/openapi.yaml`'s
    `initMediaUpload` 422 response covers both ("Unsupported media type or oversize") under one
    code, not two."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(f"size {size_bytes} exceeds the {max_bytes}-byte cap")


# --- lifecycle (I-20 QuarantinePolicy; DDD Sec 5.6 ScanStatus/ProcessingStatus) ----------------


class IllegalAssetStateTransitionError(MediaDomainError):
    """Attempted a `ScanStatus`/`ProcessingStatus` transition outside the single-shot state
    machine (DDD Sec 5.6): PENDING->{CLEAN,QUARANTINED} for scanning, PENDING->{COMPLETED,FAILED}
    for processing, both terminal once left. Also guards `complete_processing`/`fail_processing`
    against running before scanning has reached CLEAN."""

    def __init__(self, aspect: str, current: str, attempted: str) -> None:
        self.aspect = aspect
        self.current = current
        self.attempted = attempted
        super().__init__(f"cannot transition {aspect} from {current} to {attempted}")


class ScanNotCleanError(MediaDomainError):
    """`ImageProcessingService` (EXIF strip + variant generation) cannot start until
    scan_status=CLEAN (I-20: malware scan precedes any variant production; BRULE-12)."""

    def __init__(self, scan_status: str) -> None:
        self.scan_status = scan_status
        super().__init__(f"cannot process an asset with scan_status={scan_status}, must be CLEAN")


class AssetNotDeliverableError(MediaDomainError):
    """I-20 `QuarantinePolicy`: "a stored MediaAsset is image-typed, malware-clean, and
    EXIF/GPS-free; quarantined assets are never delivered." Raised when a delivery reference
    (original URL or a variant) is requested for an asset that has not reached
    scan_status=CLEAN and processing_status=COMPLETED."""


class VariantNotFoundError(MediaDomainError):
    """The asset has no `ImageVariant` of the requested `VariantKind`."""

    def __init__(self, variant_kind: str) -> None:
        self.variant_kind = variant_kind
        super().__init__(f"no {variant_kind} variant for this asset")
