"""catalog -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
operations tagged to this module (contracts/openapi.yaml). Schema only: no aggregate
type is exposed here, no business behaviour, no validation beyond what Pydantic
itself does structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from active_home_shared import CamelModel
from shared_kernel import GeoLocation, Money

AttributeMap = dict[str, Any]
"""The dynamic listing attributes (the AttributeSet, DM-02) -- typed values keyed by the
field `code` of the bound FormDefinition version (OpenAPI `AttributeMap`)."""


class PageInfo(CamelModel):
    """Cursor pagination metadata (OpenAPI `CursorPage.page`)."""

    limit: int
    next_cursor: str | None = None
    """Pass as `cursor` to fetch the next page; null when exhausted."""
    total: int | None = None
    """Present only where cheap to compute; may be null."""


class AddFavoriteBody(CamelModel):
    """OpenAPI `AddFavoriteBody`."""

    listing_id: UUID


class Favorite(CamelModel):
    """OpenAPI `Favorite`."""

    listing_id: UUID
    created_at: datetime


class ListingImage(CamelModel):
    """OpenAPI `ListingImage`."""

    id: UUID | None = None
    media_asset_id: UUID
    position: int
    """Position 1 is the primary image."""
    status: Literal["PENDING", "CLEAN", "QUARANTINED"] | None = None


class ListingStatusChangeRequest(CamelModel):
    """OpenAPI `ListingStatusChangeRequest`."""

    action: Literal["PUBLISH", "ARCHIVE", "SUSPEND", "RENEW", "RESTORE", "DELETE", "SOLD"]
    """Owner-permitted lifecycle transitions (I-05); illegal transitions return 409."""
    reason: str | None = None


class Listing(CamelModel):
    """An advertisement / product / service (BC-03 Listing). Promotion is a projection from
    entitlements."""

    id: UUID
    listing_type: Literal["ADVERTISEMENT", "PRODUCT", "SERVICE"]
    owner_user_id: UUID
    owner_profile_id: UUID | None = None
    category_id: UUID
    category_path: str | None = None
    form_definition_version_id: UUID
    """Bound form version (I-07); immutable per edit-cycle."""
    title: str
    description: str | None = None
    attributes: AttributeMap | None = None
    price: Money | None = None
    location: GeoLocation | None = None
    lifecycle_state: Literal[
        "DRAFT",
        "PENDING_VERIFICATION",
        "PUBLISHED",
        "EDITED",
        "SUSPENDED",
        "ARCHIVED",
        "DELETED",
        "SOLD",
    ]
    is_flagged: bool | None = None
    expires_at: datetime | None = None
    published_at: datetime | None = None
    promotion: ListingPromotion | None = None
    """Projected from entitlement events (X-03); labelled and capped in search."""
    images: list[ListingImage] | None = None
    slug: str
    lock_version: int | None = None
    """Optimistic-lock token; echo it on update (If-Match style)."""
    awaiting_payment: bool | None = None
    """Listing paywall (2026-08-23): `true` for a `DRAFT` listing whose publish is held pending
    payment -- the frontend opens the Paywall Modal when `createListing` returns this `true`."""
    created_at: datetime
    updated_at: datetime | None = None


class ListingPromotion(CamelModel):
    """Projected from entitlement events (X-03); labelled and capped in search."""

    kind: Literal["PREMIUM", "FEATURED", "TOP_PLACEMENT"] | None = None
    valid_until: datetime | None = None


class ListingCreateRequest(CamelModel):
    """OpenAPI `ListingCreateRequest`."""

    listing_type: Literal["ADVERTISEMENT", "PRODUCT", "SERVICE"]
    category_id: UUID
    title: str
    description: str | None = None
    attributes: AttributeMap
    price: Money | None = None
    location: GeoLocation | None = None
    image_media_asset_ids: list[UUID] | None = None
    publish: bool | None = False
    """True to publish immediately (post-publication moderation, BRULE-17); false saves a draft."""


class ListingStatistics(CamelModel):
    """Per-listing owner statistics (closed v1 metric vocabulary)."""

    listing_id: UUID | None = None
    views: int | None = None
    contact_clicks: int | None = None
    phone_reveals: int | None = None
    chats_initiated: int | None = None
    favorites: int | None = None


class FavoritePage(CamelModel):
    """A cursor-paginated page of `Favorite` (OpenAPI `CursorPage` composed with
    `items: Favorite[]` via `allOf`)."""

    items: list[Favorite]
    page: PageInfo


class ListingPage(CamelModel):
    """A cursor-paginated page of `Listing` (OpenAPI `CursorPage` composed with
    `items: Listing[]` via `allOf`)."""

    items: list[Listing]
    page: PageInfo


class ImageReorderRequest(CamelModel):
    """OpenAPI `ImageReorderRequest`."""

    order: list[UUID]
    """The full ordered list of image ids (position derives from array index; index 0 = primary)."""


class ListingUpdateRequest(CamelModel):
    """Owner edit; transitions the listing to EDITED and re-binds/re-validates against the current
    form version."""

    title: str | None = None
    description: str | None = None
    attributes: AttributeMap | None = None
    price: Money | None = None
    location: GeoLocation | None = None
    lock_version: int
    """Must match the current lockVersion or 409."""
