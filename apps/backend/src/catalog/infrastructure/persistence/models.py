"""SQLAlchemy models for catalog's Postgres-backed `Listing`/`Favorite` aggregates (Physical DB
"catalog schema" section). `ImageAttachment`/`LifecycleTransitionRecord` are child entities (DDD
Sec 5.3, `ON DELETE CASCADE`/`RESTRICT` per the physical spec) with no repository of their own --
persisted as part of `SqlalchemyListingRepository`'s unit of work, mirroring
`identity.infrastructure.persistence.models`'s `AuthenticationMethodRow`/`RoleAssignmentRow`
pattern. `SubscriptionProjectionRow` is not an aggregate -- a locally projected read model (I-08),
keyed by `owner_profile_id` alone, no `AggregateMixin`. `attribute_document` deliberately carries
no GIN index (DM-02/Physical DB "catalog schema" section: "NO GIN index on the AttributeSet
document" -- filtering/faceting on attributes is BC-05/search's job, out of this task's scope).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backbone.idempotency import make_processed_event_model
from backbone.outbox import make_outbox_event_model
from backbone.persistence import AggregateMixin, uuid7
from catalog.infrastructure.persistence.base import CatalogBase

_LISTING_TYPES = "('ADVERTISEMENT', 'PRODUCT', 'SERVICE')"
_LIFECYCLE_STATES = (
    "('DRAFT', 'PENDING_VERIFICATION', 'PUBLISHED', 'EDITED', 'SUSPENDED', 'ARCHIVED', 'DELETED')"
)
_IMAGE_STATUSES = "('PENDING', 'CLEAN', 'QUARANTINED')"
_TRANSITION_KINDS = (
    "('CREATE', 'PUBLISH', 'EDIT', 'SUSPEND', 'ARCHIVE', 'DELETE', 'EXPIRE', 'RENEW', 'FLAG', "
    "'UNFLAG', 'RESTORE')"
)
_PROMOTION_KINDS = "('PREMIUM', 'FEATURED', 'TOP_PLACEMENT')"


class ListingRow(CatalogBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "listing"

    listing_type: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    owner_profile_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    category_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    category_path: Mapped[str] = mapped_column(Text, nullable=False)
    form_definition_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    form_definition_version_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    attribute_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """DM-02: one typed JSONB document -- EAV is explicitly rejected. No GIN index (see module
    docstring)."""
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_lat: Mapped[float | None] = mapped_column(nullable=True)
    location_long: Mapped[float | None] = mapped_column(nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="DRAFT")
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    promotion_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion_valid_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    promotion_entitlement_id: Mapped[PyUUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(f"listing_type IN {_LISTING_TYPES}", name="ck_listing_listing_type"),
        CheckConstraint(
            f"lifecycle_state IN {_LIFECYCLE_STATES}", name="ck_listing_lifecycle_state"
        ),
        CheckConstraint(
            f"promotion_kind IS NULL OR promotion_kind IN {_PROMOTION_KINDS}",
            name="ck_listing_promotion_kind",
        ),
        Index("ix_listing_owner_user_id", "owner_user_id"),
        Index("ix_listing_category_id", "category_id"),
        Index(
            "ix_listing_visible",
            "lifecycle_state",
            "is_flagged",
            postgresql_where=(
                (lifecycle_state.in_(["PUBLISHED", "EDITED"])) & (is_flagged.is_(False))
            ),
        ),
    )


class ImageAttachmentRow(CatalogBase):  # type: ignore[misc,valid-type]
    """Child entity of `Listing` (DDD Sec 5.3) -- no repository of its own."""

    __tablename__ = "image_attachment"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    listing_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("catalog.listing.id", ondelete="CASCADE"), nullable=False
    )
    media_asset_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    asset_status_snapshot: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("position BETWEEN 1 AND 10", name="ck_image_attachment_position"),
        CheckConstraint(
            f"asset_status_snapshot IN {_IMAGE_STATUSES}", name="ck_image_attachment_status"
        ),
        UniqueConstraint("listing_id", "position", name="ux_image_attachment_listing_position"),
    )


class ListingTransitionRow(CatalogBase):  # type: ignore[misc,valid-type]
    """Child entity of `Listing` (DDD Sec 5.3, I-05) -- append-only (DM-06's discipline extended
    to this table); `ON DELETE RESTRICT` (Physical DB "catalog schema" section) -- the audit
    trail must never disappear as a side effect of a listing row's own lifecycle."""

    __tablename__ = "listing_transition"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    listing_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("catalog.listing.id", ondelete="RESTRICT"), nullable=False
    )
    from_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_state: Mapped[str] = mapped_column(Text, nullable=False)
    transition_kind: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            f"transition_kind IN {_TRANSITION_KINDS}", name="ck_listing_transition_kind"
        ),
        Index("ix_listing_transition_listing_id", "listing_id"),
    )


class FavoriteRow(CatalogBase):  # type: ignore[misc,valid-type]
    """`Favorite` is its own aggregate root (DDD Sec 5.3), not a `Listing` child -- physical
    `DELETE` is permitted (no soft-delete discipline, unlike `Listing`)."""

    __tablename__ = "favorite"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    listing_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("catalog.listing.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="ux_favorite_user_listing"),)


class SubscriptionProjectionRow(CatalogBase):  # type: ignore[misc,valid-type]
    """A locally projected read model of a billing entitlement (I-08) -- not an aggregate (no
    `AggregateMixin`: this row is a cache, rebuilt idempotently from billing's own outbox events,
    never itself the source of truth). Keyed by `owner_profile_id` alone (Physical DB "catalog
    schema" section)."""

    __tablename__ = "subscription_projection"

    owner_profile_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    entitlement_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_definition_id: Mapped[PyUUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    quota_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    source_event_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


OutboxEventRow: Any = make_outbox_event_model(CatalogBase)
ProcessedEventRow: Any = make_processed_event_model(CatalogBase)
