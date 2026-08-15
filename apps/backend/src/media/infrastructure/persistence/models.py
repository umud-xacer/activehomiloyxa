"""SQLAlchemy models for media's Postgres-backed `MediaAsset` aggregate (Physical DB Sec 2.6).
`ImageVariant` is a child entity (DDD Sec 5.6, `ON DELETE CASCADE`) with no repository of its
own -- persisted as part of `MediaAssetRepository`'s unit of work, mirroring
`identity.infrastructure.persistence.models`'s `AuthenticationMethodRow`/`RoleAssignmentRow`
pattern. `CheckConstraint`s mirror Physical DB Sec 2.6's column notes verbatim (the same
discipline `configuration.infrastructure.persistence.models` already applies).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backbone.outbox import make_outbox_event_model
from backbone.persistence import AggregateMixin, uuid7
from media.infrastructure.persistence.base import MediaBase

_OWNER_CONTEXT_TYPES = (
    "('LISTING', 'PROFILE_PORTFOLIO', 'VERIFICATION_DOCUMENT', 'BANNER_CREATIVE')"
)
_CONTENT_TYPES = "('image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'video/webm')"
_SCAN_STATUSES = "('PENDING', 'CLEAN', 'QUARANTINED')"
_PROCESSING_STATUSES = "('PENDING', 'COMPLETED', 'FAILED')"
_VARIANT_KINDS = "('THUMBNAIL', 'OPTIMIZED')"


class MediaAssetRow(MediaBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "media_asset"

    owner_context_type: Mapped[str] = mapped_column(Text, nullable=False)
    owner_context_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scan_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")
    processing_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")
    exif_stripped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_by: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Additive (promo-video business rule support, `profiles` module) -- see `domain.
    media_asset.MediaAsset.duration_seconds`'s own docstring."""

    __table_args__ = (
        CheckConstraint(
            f"owner_context_type IN {_OWNER_CONTEXT_TYPES}",
            name="ck_media_asset_owner_context_type",
        ),
        CheckConstraint(f"content_type IN {_CONTENT_TYPES}", name="ck_media_asset_content_type"),
        CheckConstraint("size_bytes > 0", name="ck_media_asset_size_bytes"),
        CheckConstraint(f"scan_status IN {_SCAN_STATUSES}", name="ck_media_asset_scan_status"),
        CheckConstraint(
            f"processing_status IN {_PROCESSING_STATUSES}", name="ck_media_asset_processing_status"
        ),
    )


class ImageVariantRow(MediaBase):  # type: ignore[misc,valid-type]
    """Child entity of `MediaAsset` (DDD Sec 5.6) -- no repository of its own; persisted as part
    of `MediaAssetRepository`'s unit of work."""

    __tablename__ = "image_variant"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    media_asset_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("media.media_asset.id", ondelete="CASCADE"), nullable=False
    )
    variant_kind: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    width_px: Mapped[int] = mapped_column(nullable=False)
    height_px: Mapped[int] = mapped_column(nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"variant_kind IN {_VARIANT_KINDS}", name="ck_image_variant_variant_kind"),
        UniqueConstraint("media_asset_id", "variant_kind", name="ux_image_variant_asset_kind"),
    )


OutboxEventRow: Any = make_outbox_event_model(MediaBase)
