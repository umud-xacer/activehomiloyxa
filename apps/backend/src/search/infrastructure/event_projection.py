"""Idempotent projection handlers for every event stream search consumes (X-02/X-03) -- catalog's
listing lifecycle (live producer, P-07), billing's entitlement events and profiles' verification
events (contract-only as of this task; neither module is built yet, exercised only via synthetic
`EventEnvelope`s, same precedent `catalog.infrastructure.event_projection.handle_entitlement_event`
already established for its own billing consumer).

Each handler wraps `backbone.idempotency.consumer.idempotent_consume` against search's own
`ProcessedEventRow` ledger, keyed on the *producing* event's own `event_id`, mirroring catalog's
own precedent exactly. Handlers parse the raw, untyped `EventEnvelope.payload` dict here (an
infrastructure concern) and call `IndexingUseCases`' already-typed methods (Clean Architecture:
application never touches a raw payload dict).

`SearchConfigurationChanged` (configuration) has NO handler here, deliberately: `search`'s own
`ConfigurationSnapshotPort` reads the `SearchConfiguration` snapshot LIVE on every query (no local
cache/copy) -- there is nothing for this event to invalidate. This gives a stronger guarantee than
an eventually-consistent projection would (facet/sort/cap changes apply on the very next query,
zero propagation delay) and avoids inventing a no-op handler just to have one. See
`search/README.md` for the full reasoning.

CRITICAL, CONFIRMED GAP (see `search/README.md` "Known gaps" for the full write-up): catalog's own
`ListingUseCases._listing_payload()` (Task P-07, already merged) sends only `listingId`/
`ownerUserId`/`categoryId`/`lifecycleState`/`isFlagged`/`expiresAt`/`reason` on every listing
event -- NOT the title/description/categoryPath/listingType/attributes/price/location/slug/
publishedAt that `ListingSearchDocument` documented-ly needs (DB Architecture Sec 3.5: "rebuilt
from Catalog events: text fields..."). `handle_listing_published`/`handle_listing_edited` are
written against the CORRECT, documented payload shape (raising `MalformedEventPayloadError`, not
silently skipping, if a required field is absent) -- they will not successfully index a real
listing until catalog's payload is corrected in a follow-up fix. The five visibility-only handlers
(suspend/archive/delete/expire/renew) work correctly against catalog's payload exactly as it
ships today, since they only ever needed `listingId` + a computed visibility flag.

`make_search_event_handler()`, at the bottom of this module, resolves a gap flagged in
`catalog.infrastructure.event_projection`'s own docstring: `backbone.outbox.dispatcher.
EventHandler` is `Callable[[EventEnvelope], Awaitable[None]]` -- it carries no `AsyncSession`, yet
every handler above needs one (for its own `ProcessedEventRow` ledger insert) and `IndexingUseCases`
needs one bound to its `FallbackIndexPort`. Catalog's own two handlers take `session` as a
parameter and are, per `catalog/README.md` "Known gaps", consequently never actually wired to a
dispatcher. `make_search_event_handler` instead opens and commits its OWN fresh session per event,
independent of `OutboxDispatcher.drain_once`'s own outer session (which only claims/marks outbox
rows, never sees the handler's effects). This is safe, not just expedient: if the process crashes
between the handler's own commit and the outer session marking the row `DISPATCHED`, the event is
redelivered, and `idempotent_consume`'s ledger makes that redelivery a no-op -- exactly the
at-least-once contract `OutboxDispatcher`'s own docstring promises.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backbone.idempotency import idempotent_consume
from search.application.exceptions import MalformedEventPayloadError
from search.application.indexing_use_cases import IndexingUseCases
from search.application.ports import SearchIndexPort
from search.domain import ListingType, PromotionKind, PromotionMarker
from search.infrastructure.persistence.models import ProcessedEventRow
from search.infrastructure.persistence.repository import SqlalchemyFallbackIndexRepository
from shared_kernel import EventEnvelope, GeoLocation, Money

_LISTING_HANDLER = "search.listing_projection"
_ENTITLEMENT_HANDLER = "search.entitlement_projection"
_BADGE_HANDLER = "search.verified_badge_projection"

_VISIBLE_LIFECYCLE_STATES = {"PUBLISHED", "EDITED"}


def _require(payload: dict[str, Any], field: str, event_type: str) -> Any:
    if field not in payload or payload[field] is None:
        raise MalformedEventPayloadError(event_type, field)
    return payload[field]


def _derive_publicly_visible(payload: dict[str, Any], *, now: datetime) -> bool:
    """I-06's rule, re-derived here ONLY as a fallback for events that don't carry an explicit
    `isPubliclyVisible` flag (DB Architecture Sec 3.5 documents this as a field the event SHOULD
    carry pre-computed, "carried, not computed" -- catalog's current payload doesn't send it, so
    this reimplements the same three-condition rule `catalog.domain.listing.Listing.
    is_publicly_visible` already guards, from the fields catalog's payload DOES send today)."""
    if "isPubliclyVisible" in payload:
        return bool(payload["isPubliclyVisible"])
    lifecycle_state = payload.get("lifecycleState")
    is_flagged = payload.get("isFlagged", False)
    expires_at_raw = payload.get("expiresAt")
    if lifecycle_state not in _VISIBLE_LIFECYCLE_STATES or is_flagged:
        return False
    if expires_at_raw:
        expires_at = datetime.fromisoformat(expires_at_raw)
        if expires_at <= now:
            return False
    return True


async def handle_listing_published(
    session: AsyncSession, envelope: EventEnvelope, use_cases: IndexingUseCases
) -> None:
    """`ListingPublished` -- content-bearing (X-02)."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_LISTING_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        await _upsert_content_from_payload(envelope, use_cases)


async def handle_listing_edited(
    session: AsyncSession, envelope: EventEnvelope, use_cases: IndexingUseCases
) -> None:
    """`ListingEdited` -- content-bearing (X-02)."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_LISTING_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        await _upsert_content_from_payload(envelope, use_cases)


async def _upsert_content_from_payload(
    envelope: EventEnvelope, use_cases: IndexingUseCases
) -> None:
    payload = envelope.payload
    listing_id = UUID(str(_require(payload, "listingId", envelope.event_type)))
    title = _require(payload, "title", envelope.event_type)
    category_id = UUID(str(_require(payload, "categoryId", envelope.event_type)))
    category_path = _require(payload, "categoryPath", envelope.event_type)
    listing_type = ListingType(_require(payload, "listingType", envelope.event_type))
    slug = _require(payload, "slug", envelope.event_type)

    owner_profile_id_raw = payload.get("ownerProfileId")
    price_raw = payload.get("price")
    location_raw = payload.get("location")
    published_at_raw = payload.get("publishedAt")
    primary_image_raw = payload.get("primaryImageThumbnailUrl")

    await use_cases.upsert_listing_content(
        listing_id=listing_id,
        owner_profile_id=UUID(str(owner_profile_id_raw)) if owner_profile_id_raw else None,
        title=title,
        description=payload.get("description"),
        category_id=category_id,
        category_path=category_path,
        listing_type=listing_type,
        attributes=dict(payload.get("attributes") or {}),
        price=(
            Money(amount=Decimal(str(price_raw["amount"])), currency=price_raw["currency"])
            if price_raw
            else None
        ),
        location=(
            GeoLocation(latitude=location_raw["latitude"], longitude=location_raw["longitude"])
            if location_raw
            else None
        ),
        slug=slug,
        published_at=(datetime.fromisoformat(published_at_raw) if published_at_raw else None),
        publicly_visible=_derive_publicly_visible(payload, now=envelope.occurred_at),
        primary_image_thumbnail_url=(str(primary_image_raw) if primary_image_raw else None),
        now=envelope.occurred_at,
    )

    # P-20: catalog's `_listing_payload()` now carries the listing's current `promotion`
    # projection (see composition_root's `handle_listing_promotion_event` route) -- the KEY is
    # always present once catalog's own payload is widened, `None` meaning "no active promotion".
    # `upsert_listing_content` itself deliberately never touches `promotion` (its own docstring:
    # "preserves promotion ... across a re-projection", since most callers of THIS function still
    # only carry title/description/etc.) -- applying it here, keyed on the payload literally
    # containing the field, keeps that preservation behavior for every payload shape that still
    # omits it while making catalog's own promotion projection authoritative when present.
    if "promotion" in payload:
        promotion_raw = payload["promotion"]
        if promotion_raw:
            await use_cases.apply_promotion(
                listing_id=listing_id,
                promotion=PromotionMarker(
                    kind=PromotionKind(promotion_raw["kind"]),
                    valid_until=(
                        datetime.fromisoformat(promotion_raw["validUntil"])
                        if promotion_raw.get("validUntil")
                        else None
                    ),
                    entitlement_id=UUID(str(promotion_raw["entitlementId"])),
                ),
                now=envelope.occurred_at,
            )
        else:
            await use_cases.clear_promotion(listing_id=listing_id, now=envelope.occurred_at)


async def handle_listing_visibility_event(
    session: AsyncSession, envelope: EventEnvelope, use_cases: IndexingUseCases
) -> None:
    """`ListingSuspended`/`ListingArchived`/`ListingDeleted`/`ListingExpired`/`ListingRenewed` --
    visibility-only (X-02). Never raises `MalformedEventPayloadError`: these events only ever
    needed `listingId` + the visibility-deriving fields, all of which catalog's current payload
    already sends."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_LISTING_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        payload = envelope.payload
        listing_id = UUID(str(_require(payload, "listingId", envelope.event_type)))
        publicly_visible = _derive_publicly_visible(payload, now=envelope.occurred_at)
        await use_cases.update_listing_visibility(
            listing_id=listing_id, publicly_visible=publicly_visible, now=envelope.occurred_at
        )


async def handle_entitlement_activated(
    session: AsyncSession, envelope: EventEnvelope, use_cases: IndexingUseCases
) -> None:
    """`EntitlementActivated` (billing, X-03) -- contract-only as of this task (BC-08 not yet
    built). Assumed payload shape (no live producer to confirm against): `listingId`, `kind`
    (PREMIUM/FEATURED/TOP_PLACEMENT), `validUntil` (nullable), `entitlementId` -- a defensible,
    minimal reading of "promotion boosts... sourced from Billing" (DEC-12) for a listing-scoped
    entitlement; flagged in README "Known gaps" pending BC-08's own frozen payload contract."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_ENTITLEMENT_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        payload = envelope.payload
        listing_id = UUID(str(_require(payload, "listingId", envelope.event_type)))
        kind = PromotionKind(_require(payload, "kind", envelope.event_type))
        entitlement_id = UUID(str(_require(payload, "entitlementId", envelope.event_type)))
        valid_until_raw = payload.get("validUntil")
        await use_cases.apply_promotion(
            listing_id=listing_id,
            promotion=PromotionMarker(
                kind=kind,
                valid_until=(datetime.fromisoformat(valid_until_raw) if valid_until_raw else None),
                entitlement_id=entitlement_id,
            ),
            now=envelope.occurred_at,
        )


async def handle_entitlement_cleared(
    session: AsyncSession, envelope: EventEnvelope, use_cases: IndexingUseCases
) -> None:
    """`EntitlementExpired`/`EntitlementRevoked` (billing, X-03) -- contract-only."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_ENTITLEMENT_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        payload = envelope.payload
        listing_id = UUID(str(_require(payload, "listingId", envelope.event_type)))
        await use_cases.clear_promotion(listing_id=listing_id, now=envelope.occurred_at)


async def handle_verified_badge_applied(
    session: AsyncSession, envelope: EventEnvelope, use_cases: IndexingUseCases
) -> None:
    """`BusinessVerified` (profiles, X-03) -- contract-only as of this task (BC-02 not yet
    built). Assumed payload field: `businessProfileId`."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_BADGE_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        owner_profile_id = UUID(
            str(_require(envelope.payload, "businessProfileId", envelope.event_type))
        )
        await use_cases.apply_verified_badge(
            owner_profile_id=owner_profile_id, verified_badge=True, now=envelope.occurred_at
        )


async def handle_verified_badge_cleared(
    session: AsyncSession, envelope: EventEnvelope, use_cases: IndexingUseCases
) -> None:
    """`VerificationRejected`/`VerifiedBadgeExpired` (profiles, X-03) -- contract-only. Both
    always CLEAR the badge (idempotent no-op if already unset) rather than distinguishing "never
    verified" from "verification lost" -- either way the end state is "not verified", which is
    all `ListingSearchDocument.verified_badge` represents."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_BADGE_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        owner_profile_id = UUID(
            str(_require(envelope.payload, "businessProfileId", envelope.event_type))
        )
        await use_cases.apply_verified_badge(
            owner_profile_id=owner_profile_id, verified_badge=False, now=envelope.occurred_at
        )


_CONTENT_EVENT_TYPES = {"ListingPublished", "ListingEdited"}
_VISIBILITY_EVENT_TYPES = {
    "ListingSuspended",
    "ListingArchived",
    "ListingDeleted",
    "ListingExpired",
    "ListingRenewed",
}
_ENTITLEMENT_ACTIVATED_EVENT_TYPES = {"EntitlementActivated"}
_ENTITLEMENT_CLEARED_EVENT_TYPES = {"EntitlementExpired", "EntitlementRevoked"}
_BADGE_APPLIED_EVENT_TYPES = {"BusinessVerified"}
_BADGE_CLEARED_EVENT_TYPES = {"VerificationRejected", "VerifiedBadgeExpired"}


async def dispatch_search_event(
    session: AsyncSession, envelope: EventEnvelope, use_cases: IndexingUseCases
) -> None:
    """Routes one envelope to its typed handler by `event_type`, against an already-open
    `session`. Used directly by tests (one shared session per assertion) and by
    `make_search_event_handler`'s per-event session below."""
    if envelope.event_type in _CONTENT_EVENT_TYPES:
        if envelope.event_type == "ListingPublished":
            await handle_listing_published(session, envelope, use_cases)
        else:
            await handle_listing_edited(session, envelope, use_cases)
    elif envelope.event_type in _VISIBILITY_EVENT_TYPES:
        await handle_listing_visibility_event(session, envelope, use_cases)
    elif envelope.event_type in _ENTITLEMENT_ACTIVATED_EVENT_TYPES:
        await handle_entitlement_activated(session, envelope, use_cases)
    elif envelope.event_type in _ENTITLEMENT_CLEARED_EVENT_TYPES:
        await handle_entitlement_cleared(session, envelope, use_cases)
    elif envelope.event_type in _BADGE_APPLIED_EVENT_TYPES:
        await handle_verified_badge_applied(session, envelope, use_cases)
    elif envelope.event_type in _BADGE_CLEARED_EVENT_TYPES:
        await handle_verified_badge_cleared(session, envelope, use_cases)
    # ListingCreated/ListingDraftSaved/ListingFlagged/FavoriteAdded/FavoriteRemoved and any other
    # event_type: no documented Search consumer (Domain Model Sec 6's own events table) --
    # silently ignored, not an error (an unhandled event_type here is expected, not malformed).


def make_search_event_handler(
    *, session_factory: async_sessionmaker[AsyncSession], index: SearchIndexPort
) -> Callable[[EventEnvelope], Awaitable[None]]:
    """Builds a `backbone.outbox.dispatcher.EventHandler`-shaped callable: one closure the
    composition root can attach to any producing module's own `OutboxDispatcher` (catalog's
    today; billing's/profiles' once P-09/P-11 exist) -- `dispatch_search_event` above already
    routes correctly regardless of which module's outbox the envelope came from. `index` (the
    OpenSearch adapter) holds no per-request state and is shared across every call; the
    `FallbackIndexPort`/`IndexingUseCases` pair is rebuilt fresh each call, bound to a session
    that is opened, committed, and closed entirely within this one event's handling -- see this
    module's own top docstring for why that is the correct (not merely convenient) choice."""

    async def _handle(envelope: EventEnvelope) -> None:
        async with session_factory() as session, session.begin():
            fallback = SqlalchemyFallbackIndexRepository(session)
            use_cases = IndexingUseCases(index=index, fallback=fallback)
            await dispatch_search_event(session, envelope, use_cases)

    return _handle
