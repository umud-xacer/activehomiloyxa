"""search/application -- `IndexingUseCases` (Task P-08): `IndexingProjectionService [P]`'s own
application-layer half. Every method here is plain, non-idempotent-aware business logic --
idempotent redelivery-safety (the `ProcessedEvent` ledger) is an infrastructure concern, applied
by `infrastructure/event_projection.py`'s handlers, which parse the raw event payload and call
these methods with already-typed arguments (Clean Architecture: application never touches
`dict[str, Any]` payloads or `EventEnvelope` directly).

Every method writes to BOTH `SearchIndexPort` (OpenSearch, primary) and `FallbackIndexPort`
(search's own Postgres fallback table) -- one projection, two sinks, populated together so the
fallback never lags the primary index (see `search/README.md` for why the fallback is
search-owned rather than a read against `catalog.listing`)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from search.application.ports import FallbackIndexPort, SearchIndexPort
from search.domain import ListingSearchDocument, ListingType, PromotionMarker
from shared_kernel import GeoLocation, Money


class IndexingUseCases:
    def __init__(self, *, index: SearchIndexPort, fallback: FallbackIndexPort) -> None:
        self._index = index
        self._fallback = fallback

    async def upsert_listing_content(
        self,
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
        slug: str,
        published_at: datetime | None,
        publicly_visible: bool,
        now: datetime,
        primary_image_thumbnail_url: str | None = None,
    ) -> None:
        """`ListingPublished`/`ListingEdited` -- the only two events carrying full content.
        Preserves `promotion`/`verified_badge` across a re-projection by reading the existing
        document first (those fields are owned by their own dedicated projection events, X-03,
        never by catalog's own content events)."""
        existing = await self._index.get_document(listing_id)
        if existing is None:
            document = ListingSearchDocument.project(
                listing_id=listing_id,
                owner_profile_id=owner_profile_id,
                title=title,
                description=description,
                category_id=category_id,
                category_path=category_path,
                listing_type=listing_type,
                attributes=attributes,
                price=price,
                location=location,
                verified_badge=False,
                publicly_visible=publicly_visible,
                slug=slug,
                published_at=published_at,
                updated_at=now,
                primary_image_thumbnail_url=primary_image_thumbnail_url,
            )
        else:
            document = existing.with_content(
                title=title,
                description=description,
                category_id=category_id,
                category_path=category_path,
                attributes=attributes,
                price=price,
                location=location,
                publicly_visible=publicly_visible,
                updated_at=now,
                primary_image_thumbnail_url=primary_image_thumbnail_url,
            )
        await self._index.index_document(document)
        await self._fallback.upsert_document(document)

    async def update_listing_visibility(
        self, *, listing_id: UUID, publicly_visible: bool, now: datetime
    ) -> None:
        """`ListingSuspended`/`ListingArchived`/`ListingDeleted`/`ListingExpired`/
        `ListingRenewed` -- lifecycle-only transitions that never carry content. A no-op if the
        listing has no indexed document yet (nothing to hide -- mirrors `catalog.domain.listing.
        Listing.update_image_status`'s own redelivery-safe, no-op-if-not-attached precedent).
        `ListingDeleted` is handled here too, not as a hard index removal: DM-06's "Deleted is a
        state, never a row removal" discipline extends naturally to this projection -- the
        deleted listing's own events remain replayable, and `publicly_visible=False` already
        fully satisfies "a deleted listing never appears in results" without a second code path."""
        document = await self._index.get_document(listing_id)
        if document is None:
            return
        updated = document.with_visibility(publicly_visible=publicly_visible, updated_at=now)
        await self._index.index_document(updated)
        await self._fallback.upsert_document(updated)

    async def apply_promotion(
        self, *, listing_id: UUID, promotion: PromotionMarker, now: datetime
    ) -> None:
        """`EntitlementActivated` (billing, X-03) -- contract-only as of this task (BC-08 not yet
        built); exercised via synthetic events, same precedent as `catalog.infrastructure.
        event_projection.handle_entitlement_event`. No-op if undexed yet, same reasoning as
        `update_listing_visibility`."""
        document = await self._index.get_document(listing_id)
        if document is None:
            return
        updated = document.with_promotion(promotion=promotion, updated_at=now)
        await self._index.index_document(updated)
        await self._fallback.upsert_document(updated)

    async def clear_promotion(self, *, listing_id: UUID, now: datetime) -> None:
        """`EntitlementExpired`/`EntitlementRevoked` (billing, X-03)."""
        document = await self._index.get_document(listing_id)
        if document is None:
            return
        updated = document.with_promotion(promotion=None, updated_at=now)
        await self._index.index_document(updated)
        await self._fallback.upsert_document(updated)

    async def apply_verified_badge(
        self, *, owner_profile_id: UUID, verified_badge: bool, now: datetime
    ) -> None:
        """`BusinessVerified`/`VerificationRejected`/`VerifiedBadgeExpired` (profiles, X-03) --
        contract-only as of this task (BC-02 not yet built). One event affects every listing
        owned by `owner_profile_id`, not a single `listing_id` -- fans out via
        `find_listing_ids_by_owner_profile`."""
        listing_ids = await self._index.find_listing_ids_by_owner_profile(owner_profile_id)
        for listing_id in listing_ids:
            document = await self._index.get_document(listing_id)
            if document is None:
                continue
            updated = document.with_verified_badge(verified_badge=verified_badge, updated_at=now)
            await self._index.index_document(updated)
            await self._fallback.upsert_document(updated)
