"""media -- the `MediaAsset` aggregate (DDD Sec 5.6 `AR: MediaAsset [P]`). Persistence-ignorant,
mirrors `identity.domain.user_account`'s style: frozen dataclass, every state transition returns
a new instance via `dataclasses.replace`, guarded by a typed exception raised before the
replace. `ImageVariant` is a child entity inside this aggregate's boundary (DDD Sec 5.6 "set of
ImageVariant"), so one repository/one transaction covers the asset and its variants together.

Encodes I-20 ("a stored MediaAsset is image-typed, malware-clean, and EXIF/GPS-free; quarantined
assets are never delivered") as a state machine, not a runtime byte-level check -- the actual
scanning/EXIF-stripping/encoding happens in `infrastructure/` adapters behind `MalwareScanPort`/
`StoragePort`; the aggregate's job is to make "delivery available" *unreachable* except by
passing through scan_status=CLEAN and processing_status=COMPLETED, in that order.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from media.domain.exceptions import (
    AssetNotDeliverableError,
    IllegalAssetStateTransitionError,
    OversizeMediaError,
    ScanNotCleanError,
    UnsupportedMediaTypeError,
    VariantNotFoundError,
)
from media.domain.image_variant import ImageVariant
from media.domain.value_objects import (
    EXTENSION_BY_CONTENT_TYPE,
    ContentType,
    OwnerContextType,
    ProcessingStatus,
    ScanStatus,
    VariantKind,
    max_size_bytes_for,
)
from shared_kernel import MediaAssetId, UserId


def _storage_key_for(asset_id: MediaAssetId, content_type: ContentType) -> str:
    """Security Sec 7 "storage keys are opaque and never exposed as identity": built from the
    asset's own already-public id rather than from a separately-invented opaque token, so the
    key format never leaks information beyond what `id` alone already discloses. Never
    serialized to a DTO -- see `interfaces/` for the public delivery-URL construction."""
    return f"media/{asset_id.value}/original{EXTENSION_BY_CONTENT_TYPE[content_type]}"


@dataclass(frozen=True)
class MediaAsset:
    """`lock_version` matches `backbone.persistence.AggregateMixin`'s optimistic-locking column.
    `owner_context_id` stays `None` for the whole of this task's scope: `contracts/openapi.yaml`'s
    `MediaUploadInitRequest` carries only `ownerContextType`, and no v1 operation associates an
    asset with a specific owning aggregate instance afterwards -- Physical DB Sec 2.6 documents
    the column as "set on association; NULL while pending association", and that association
    step belongs to the future consuming-context task (catalog/profiles/ads), not this one."""

    id: MediaAssetId
    owner_context_type: OwnerContextType
    owner_context_id: UUID | None
    storage_key: str
    content_type: ContentType
    size_bytes: int
    scan_status: ScanStatus
    processing_status: ProcessingStatus
    exif_stripped: bool
    uploaded_by: UserId
    variants: tuple[ImageVariant, ...]
    created_at: datetime
    updated_at: datetime
    lock_version: int = 0
    duration_seconds: float | None = None
    """Additive (promo-video business rule support, `profiles` module): the container's own
    declared duration, populated only for `video/mp4`/`video/webm` by `complete_processing` --
    `None` for every image/GIF asset (unaffected) and for a video whose duration could not be
    confidently read (see `infrastructure.video_probe`'s own docstring)."""

    # --- factory (FR-MEDIA-001/002, ImageOnlyPolicy [P] + the size cap) ----------------------

    @staticmethod
    def initiate(
        *,
        asset_id: MediaAssetId,
        content_type_raw: str,
        size_bytes: int,
        owner_context_type: OwnerContextType,
        uploaded_by: UserId,
        now: datetime,
    ) -> MediaAsset:
        """`MediaIntakeService`: validates type/size before admitting the asset (I-04's own
        image-*count* cap is a `Listing`-side invariant, out of this module's scope -- see
        `media/README.md`). Raises `UnsupportedMediaTypeError`/`OversizeMediaError`, both mapped
        to 422 `UNSUPPORTED_MEDIA_TYPE` (`contracts/openapi.yaml`'s `initMediaUpload` 422:
        "Unsupported media type or oversize")."""
        try:
            content_type = ContentType(content_type_raw)
        except ValueError:
            raise UnsupportedMediaTypeError(content_type_raw) from None
        max_bytes = max_size_bytes_for(content_type)
        if size_bytes <= 0 or size_bytes > max_bytes:
            raise OversizeMediaError(size_bytes, max_bytes)
        return MediaAsset(
            id=asset_id,
            owner_context_type=owner_context_type,
            owner_context_id=None,
            storage_key=_storage_key_for(asset_id, content_type),
            content_type=content_type,
            size_bytes=size_bytes,
            scan_status=ScanStatus.PENDING,
            processing_status=ProcessingStatus.PENDING,
            exif_stripped=False,
            uploaded_by=uploaded_by,
            variants=(),
            created_at=now,
            updated_at=now,
        )

    # --- scanning (FR-MEDIA-004; single-shot PENDING -> {CLEAN, QUARANTINED}) ----------------

    def mark_scanned_clean(self, *, now: datetime) -> MediaAsset:
        if self.scan_status is not ScanStatus.PENDING:
            raise IllegalAssetStateTransitionError(
                "scan_status", self.scan_status.value, ScanStatus.CLEAN.value
            )
        return replace(self, scan_status=ScanStatus.CLEAN, updated_at=now)

    def quarantine(self, *, now: datetime) -> MediaAsset:
        """I-20 `QuarantinePolicy`: covers both a positive malware-scan result and a magic-byte/
        declared-type mismatch (Security Sec 7 T-6: "quarantine on failure") -- the frozen
        `ScanStatus` vocabulary has no separate "rejected" value, so both failure modes converge
        on QUARANTINED, the one terminal "never delivered" state."""
        if self.scan_status is not ScanStatus.PENDING:
            raise IllegalAssetStateTransitionError(
                "scan_status", self.scan_status.value, ScanStatus.QUARANTINED.value
            )
        return replace(self, scan_status=ScanStatus.QUARANTINED, updated_at=now)

    # --- processing (FR-MEDIA-003/005; requires CLEAN; single-shot PENDING -> {COMPLETED, FAILED}) -

    def complete_processing(
        self,
        *,
        variants: tuple[ImageVariant, ...],
        now: datetime,
        duration_seconds: float | None = None,
    ) -> MediaAsset:
        """`ImageProcessingService`: EXIF/GPS strip + variant generation, both committed
        atomically here (BRULE-12 / Physical DB `exif_stripped` "must be true before any variant
        row exists" -- there is no intermediate state where `exif_stripped=True` but variants
        are still empty, or vice versa). `duration_seconds` is additive and defaults to `None`,
        unchanged from before it existed for every existing (image/GIF) call site."""
        if self.scan_status is not ScanStatus.CLEAN:
            raise ScanNotCleanError(self.scan_status.value)
        if self.processing_status is not ProcessingStatus.PENDING:
            raise IllegalAssetStateTransitionError(
                "processing_status", self.processing_status.value, ProcessingStatus.COMPLETED.value
            )
        return replace(
            self,
            processing_status=ProcessingStatus.COMPLETED,
            exif_stripped=True,
            variants=variants,
            duration_seconds=duration_seconds,
            updated_at=now,
        )

    def fail_processing(self, *, now: datetime) -> MediaAsset:
        """`NonBlockingPolicy` (QR-05): a processing failure is terminal for this asset but never
        raised back to block whatever created it -- the worker catches this at the call site."""
        if self.scan_status is not ScanStatus.CLEAN:
            raise ScanNotCleanError(self.scan_status.value)
        if self.processing_status is not ProcessingStatus.PENDING:
            raise IllegalAssetStateTransitionError(
                "processing_status", self.processing_status.value, ProcessingStatus.FAILED.value
            )
        return replace(self, processing_status=ProcessingStatus.FAILED, updated_at=now)

    # --- delivery gate (I-20 QuarantinePolicy) -----------------------------------------------

    @property
    def is_delivery_available(self) -> bool:
        """I-20: image-typed is guaranteed by construction (`initiate`'s `ImageOnlyPolicy`
        check); malware-clean is `scan_status is CLEAN`; EXIF/GPS-free is `processing_status is
        COMPLETED` (EXIF stripping happens during processing, before variants are produced) --
        both conditions gate the *original* as well as every variant, not variants alone (the
        stricter, safer reading of `contracts/openapi.yaml`'s `MediaAsset.url` docstring, which
        the OpenAPI spec's own wording under-specifies)."""
        return (
            self.scan_status is ScanStatus.CLEAN
            and self.processing_status is ProcessingStatus.COMPLETED
        )

    def require_delivery_available(self) -> None:
        if not self.is_delivery_available:
            raise AssetNotDeliverableError()

    def variant(self, kind: VariantKind) -> ImageVariant:
        for candidate in self.variants:
            if candidate.variant_kind is kind:
                return candidate
        raise VariantNotFoundError(kind.value)
