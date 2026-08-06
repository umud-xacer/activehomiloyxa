"""search -- `ListingSearchDocument [P]` (DDD Sec 5.5; DB Architecture Sec 3.5/Sec 12). The
denormalised discovery document -- NOT an aggregate ("no invariants beyond idempotent upsert",
Domain Model Sec 5.5's own words). Built exclusively from event-payload fields (X-02); this
module never imports `catalog`, so every field here traces to a name a frozen
`contracts/events/catalog.py` payload could plausibly carry, never to catalog's own domain types.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from search.domain.cross_script import normalize_for_matching
from search.domain.value_objects import ListingType, PromotionMarker
from shared_kernel import GeoLocation, Money


@dataclass(frozen=True)
class ListingSearchDocument:
    """One row per `listingId` (DB Architecture Sec 3.5: "derived 1 -> 1 from Listing via events
    only; no back-references"). `publicly_visible` is projected verbatim from the producing
    event's own payload flag, never re-derived here -- I-06 ("Published/Edited, unflagged,
    unexpired") is catalog's own authoritative rule; search trusts what the event says rather
    than re-implementing that predicate against data it doesn't own (DB Architecture Sec 3.5's
    own field list names this "public visibility flag (I-06)" as a carried, not computed, field)."""

    listing_id: UUID
    owner_profile_id: UUID | None
    """Carried straight from the producing event's own payload -- never a foreign business type,
    just an id. Needed so the verified-badge fan-out (`BusinessVerified`/`VerificationRejected`/
    `VerifiedBadgeExpired`, X-03) can find every listing owned by the newly-(un)verified profile
    without search holding any other profile data; `None` for a personal (non-business-profile)
    listing, which by definition never carries a verified badge."""
    title: str
    title_normalized_latin: str
    title_normalized_cyrillic: str
    description: str | None
    category_id: UUID
    category_path: str
    listing_type: ListingType
    attributes: dict[str, Any]
    """Facet-relevant subset only, keyed by field_code (DB Architecture Sec 12: "facet attributes
    = exactly the facet-eligible field codes selected in the SearchConfiguration snapshot")."""
    price: Money | None
    location: GeoLocation | None
    promotion: PromotionMarker | None
    verified_badge: bool
    publicly_visible: bool
    slug: str
    published_at: datetime | None
    updated_at: datetime
    primary_image_thumbnail_url: str | None = None
    """Delivery URL of the THUMBNAIL variant of the listing's first CLEAN image, carried verbatim
    from the producing event's payload like every other field here.

    A resolved URL rather than a `MediaAssetRef` on purpose. Search may not import `media`
    (SAD Sec 8.1), and the variant's filename extension follows the *source* image's format
    (`thumbnail.png` for a PNG upload, `.jpg` for a JPEG) -- so a ref could only be turned back
    into a URL by guessing that extension. Catalog resolves it once, at emit time, through the
    `MediaAssetReaderPort` it already owns. Trade-off: re-pointing `MEDIA_CDN_BASE_URL` needs a
    reindex to take effect on result cards. `None` for a listing with no image, or with none
    scanned CLEAN yet -- both ordinary states the interface renders a placeholder for."""

    @staticmethod
    def project(
        *,
        listing_id: UUID,
        owner_profile_id: UUID | None,
        title: str,
        description: str | None,
        category_id: UUID,
        category_path: str,
        listing_type: ListingType,
        attributes: dict[str, Any],
        price: Money | None,
        location: GeoLocation | None,
        verified_badge: bool,
        publicly_visible: bool,
        slug: str,
        published_at: datetime | None,
        updated_at: datetime,
        promotion: PromotionMarker | None = None,
        primary_image_thumbnail_url: str | None = None,
    ) -> ListingSearchDocument:
        """The one place a `ListingSearchDocument` is constructed from scratch -- computes the
        cross-script shadow fields (FR-SRCH-004) at projection time, not at query time, so every
        query only ever normalizes the (short) query string, never re-normalizes every candidate
        document's title on each search."""
        title_latin, title_cyrillic = normalize_for_matching(title)
        return ListingSearchDocument(
            listing_id=listing_id,
            owner_profile_id=owner_profile_id,
            title=title,
            title_normalized_latin=title_latin,
            title_normalized_cyrillic=title_cyrillic,
            description=description,
            category_id=category_id,
            category_path=category_path,
            listing_type=listing_type,
            attributes=attributes,
            price=price,
            location=location,
            promotion=promotion,
            verified_badge=verified_badge,
            publicly_visible=publicly_visible,
            slug=slug,
            published_at=published_at,
            updated_at=updated_at,
            primary_image_thumbnail_url=primary_image_thumbnail_url,
        )

    def with_content(
        self,
        *,
        title: str,
        description: str | None,
        category_id: UUID,
        category_path: str,
        attributes: dict[str, Any],
        price: Money | None,
        location: GeoLocation | None,
        publicly_visible: bool,
        updated_at: datetime,
        primary_image_thumbnail_url: str | None = None,
    ) -> ListingSearchDocument:
        """Re-projects content fields (`ListingEdited`/lifecycle-transition events) -- recomputes
        the cross-script shadow fields since the title may have changed; leaves `promotion`/
        `verified_badge` untouched (those are updated only by their own dedicated projection
        events, X-03).

        `primary_image_thumbnail_url` rides with content rather than getting its own `with_*`
        helper: catalog re-emits the whole listing payload on attach/detach (there is no
        image-only event in the v1 catalogue), so it always arrives alongside the other content
        fields and would go stale if this method left it untouched."""
        title_latin, title_cyrillic = normalize_for_matching(title)
        return replace(
            self,
            title=title,
            title_normalized_latin=title_latin,
            title_normalized_cyrillic=title_cyrillic,
            description=description,
            category_id=category_id,
            category_path=category_path,
            attributes=attributes,
            price=price,
            location=location,
            publicly_visible=publicly_visible,
            updated_at=updated_at,
            primary_image_thumbnail_url=primary_image_thumbnail_url,
        )

    def with_visibility(
        self, *, publicly_visible: bool, updated_at: datetime
    ) -> ListingSearchDocument:
        """Lifecycle-only transitions (suspend/archive/delete/expire/renew) that change visibility
        without touching content."""
        return replace(self, publicly_visible=publicly_visible, updated_at=updated_at)

    def with_promotion(
        self, *, promotion: PromotionMarker | None, updated_at: datetime
    ) -> ListingSearchDocument:
        """Billing entitlement projection (X-03) -- promotion state changes independently of
        content/lifecycle events."""
        return replace(self, promotion=promotion, updated_at=updated_at)

    def with_verified_badge(
        self, *, verified_badge: bool, updated_at: datetime
    ) -> ListingSearchDocument:
        """Profiles verification-badge projection (X-03)."""
        return replace(self, verified_badge=verified_badge, updated_at=updated_at)
