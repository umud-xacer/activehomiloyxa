"""Idempotent projection handlers for the event streams catalog consumes but never imports the
producer of (I-08/X-06): media's `MediaAssetReady`/`MediaAssetRejected` (image scan-status
projection), billing's entitlement events -- `handle_entitlement_event` (subscription/quota
projection, `ACTIVE_SUBSCRIPTION` only) and `handle_listing_promotion_event` (`LISTING_PROMOTION`
only, P-20 -- wired end to end via `composition_root.make_billing_entitlement_fanout_handler`,
closing the "Catalog (promotion/quota)" consumer the frozen event contract's own
`EntitlementActivated` docstring names) -- and (Task P-12) identity's `AccountSuspended` (DB
Architecture Sec 14.4's own worked example: "account suspension -> listings hidden by catalog's
own transition" -- a compensation, never a cascade written by moderation or identity).

Each handler wraps `backbone.idempotency.consumer.idempotent_consume` against catalog's own
`ProcessedEventRow` ledger, keyed on the *producing* event's own `event_id` -- redelivery of the
same event is a no-op, never a duplicate side effect (Logical Sec 18 "idempotency is data").
Handlers are plain functions taking an already-open `AsyncSession` and a `shared_kernel.
EventEnvelope`, matching `backbone.outbox.dispatcher.EventHandler`'s shape exactly, so a
`backbone.outbox.OutboxDispatcher` can drive either one directly -- the composition root
(the only place allowed to see both modules' internals) is responsible for constructing that
dispatcher against the *producing* module's own outbox model (see this module's own docstring on
why that wiring cannot live inside `catalog.infrastructure` itself).

There is no existing precedent in this codebase for one module's dispatcher draining *another*
module's `outbox_event` table, and `OutboxDispatcher`'s own `dispatch_status` column is a single
mutable field -- only one dispatcher can safely claim a given row. Wiring this dispatcher against
media's `outbox_event` table only makes sense today because media itself does not yet run any
other dispatcher against it (P-06 built no drain-side consumer); a future task adding a second
independent consumer of media's outbox would need a different mechanism (e.g. a per-consumer
cursor/fan-out table) -- flagged here and in catalog/README.md rather than silently redesigned.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from backbone.idempotency import idempotent_consume
from catalog.application.ports import SubscriptionSnapshot
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.value_objects import ImageStatus, PromotionKind
from catalog.infrastructure.persistence import ProcessedEventRow
from catalog.infrastructure.persistence.repository import (
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from shared_kernel import BusinessProfileId, ListingId, UserId

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from catalog.application.listing_use_cases import ListingUseCases
    from shared_kernel import EventEnvelope

_MEDIA_STATUS_HANDLER = "catalog.media_asset_status_projection"
_ENTITLEMENT_HANDLER = "catalog.entitlement_projection"
_LISTING_PROMOTION_HANDLER = "catalog.listing_promotion_projection"
_SUBSCRIPTION_VISIBILITY_HANDLER = "catalog.subscription_visibility_projection"
_TRIAL_SUBSCRIPTION_HANDLER = "catalog.trial_subscription_visibility_projection"
_IDENTITY_HANDLER = "catalog.identity_account_suspension_projection"

_MEDIA_STATUS_BY_EVENT_TYPE = {
    "MediaAssetReady": ImageStatus.CLEAN,
    "MediaAssetRejected": ImageStatus.QUARANTINED,
}


async def handle_media_event(session: AsyncSession, envelope: EventEnvelope) -> None:
    """X-06: projects media's own scan/processing outcome onto whichever listing currently holds
    this asset attached (`Listing.update_image_status`'s own redelivery-safe, no-op-if-not-
    attached docstring handles the "arrived late / no longer attached" case; this handler only
    owns not-applying-the-same-event-twice). Calls `SqlalchemyListingRepository` directly rather
    than through `catalog.application.ListingUseCases.apply_media_status_projection` -- that
    method's own logic is these same four lines, but its constructor also demands `categories`/
    `settings`/`media`/`quota`/`duplicates` collaborators this narrow, worker-only path never
    touches; the actual business rule being applied lives in `Listing.update_image_status`
    (domain), not duplicated here."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_MEDIA_STATUS_HANDLER,
    ) as is_fresh:
        if not is_fresh:
            return
        status = _MEDIA_STATUS_BY_EVENT_TYPE.get(envelope.event_type)
        if status is None:
            return
        media_asset_id = UUID(str(envelope.payload["mediaAssetId"]))
        listings = SqlalchemyListingRepository(session)
        listing = await listings.get_by_image_media_asset_id(media_asset_id)
        if listing is None:
            return
        updated = listing.update_image_status(
            media_asset_id=media_asset_id, status=status, now=envelope.occurred_at
        )
        if updated is listing:
            return
        await listings.save(updated)


async def handle_entitlement_event(session: AsyncSession, envelope: EventEnvelope) -> None:
    """I-08: projects a billing entitlement event into `catalog.subscription_projection` --
    catalog never imports billing (AIR-10); this is the async, outbox-driven, one-way read side
    of that boundary. Not wired to a real producer as of this task (BC-08 does not exist);
    exercised via synthetic `EventEnvelope`s in tests, the same pattern
    `test_dispatcher_idempotency.py` (backbone) already establishes."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_ENTITLEMENT_HANDLER,
    ) as is_fresh:
        if not is_fresh:
            return
        payload = envelope.payload
        owner_profile_id = payload.get("ownerProfileId")
        entitlement_id = payload.get("entitlementId")
        if owner_profile_id is None or entitlement_id is None:
            return
        valid_until_raw = payload.get("validUntil")
        product_definition_id_raw = payload.get("productDefinitionId")
        snapshot = SubscriptionSnapshot(
            owner_profile_id=BusinessProfileId(value=UUID(str(owner_profile_id))),
            entitlement_id=UUID(str(entitlement_id)),
            product_definition_id=(
                UUID(str(product_definition_id_raw)) if product_definition_id_raw else None
            ),
            quota_document=dict(payload.get("quota") or {}),
            valid_until=(datetime.fromisoformat(str(valid_until_raw)) if valid_until_raw else None),
            source_event_id=envelope.event_id,
        )
        quota = QuotaEnforcementService(
            subscriptions=SqlalchemySubscriptionSnapshotRepository(session)
        )
        await quota.apply_entitlement_projection(snapshot)


async def handle_listing_promotion_event(
    session: AsyncSession, envelope: EventEnvelope, use_cases: ListingUseCases
) -> None:
    """P-20: the `LISTING_PROMOTION` slice of billing's `EntitlementActivated`/`EntitlementExpired`/
    `EntitlementRevoked` (the frozen event contract's own `EntitlementActivated` docstring:
    "Principal consumers: Catalog (promotion/quota)...") -- distinct from `handle_entitlement_event`
    above, which only ever handles the `ACTIVE_SUBSCRIPTION` slice (a different id space:
    `ownerProfileId` there vs. `listingId` here). Applies `ListingUseCases.
    apply_promotion_projection`/`clear_promotion_projection`, which republishes `ListingEdited` so
    search's already-built listing-content consumer picks up the promotion change through the
    ordinary channel (`listing_use_cases.py`'s own docstring on those two methods)."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_LISTING_PROMOTION_HANDLER,
    ) as is_fresh:
        if not is_fresh:
            return
        payload = envelope.payload
        listing_id_raw = payload.get("listingId")
        if listing_id_raw is None:
            return
        listing_id = ListingId(value=UUID(str(listing_id_raw)))
        if envelope.event_type == "EntitlementActivated":
            kind_raw = payload.get("kind")
            valid_until_raw = payload.get("validUntil")
            entitlement_id_raw = payload.get("entitlementId")
            if kind_raw is None or valid_until_raw is None or entitlement_id_raw is None:
                return
            await use_cases.apply_promotion_projection(
                listing_id=listing_id,
                kind=PromotionKind(kind_raw),
                valid_until=datetime.fromisoformat(str(valid_until_raw)),
                entitlement_id=UUID(str(entitlement_id_raw)),
                now=envelope.occurred_at,
            )
        else:
            await use_cases.clear_promotion_projection(
                listing_id=listing_id, now=envelope.occurred_at
            )


async def handle_subscription_visibility_event(
    session: AsyncSession, envelope: EventEnvelope, use_cases: ListingUseCases
) -> None:
    """The `ACTIVE_SUBSCRIPTION` slice of billing's `EntitlementActivated`/`EntitlementExpired`/
    `EntitlementRevoked`, distinct from `handle_entitlement_event` above (which only ever updates
    the `subscription_projection` quota snapshot and, per its own docstring, deliberately has no
    withdrawal path). A legal-entity business profile's listings must be hidden from the public
    catalog while its subscription has lapsed and reappear once it's renewed -- `ListingUseCases.
    suspend_all_by_owner_profile`/`reactivate_all_by_owner_profile` (the SAME `suspend()`/
    `restore()` domain transitions an owner-invoked `changeListingStatus` would use, just
    triggered by this reaction instead of a request, mirroring `handle_identity_event`'s own
    "compensation, never a cascade" shape below) do carry a withdrawal path, so all three event
    types are routed here."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_SUBSCRIPTION_VISIBILITY_HANDLER,
    ) as is_fresh:
        if not is_fresh:
            return
        owner_profile_id_raw = envelope.payload.get("ownerProfileId")
        if owner_profile_id_raw is None:
            return
        owner_profile_id = BusinessProfileId(value=UUID(str(owner_profile_id_raw)))
        if envelope.event_type == "EntitlementActivated":
            await use_cases.reactivate_all_by_owner_profile(
                owner_profile_id=owner_profile_id, now=envelope.occurred_at
            )
        else:
            await use_cases.suspend_all_by_owner_profile(
                owner_profile_id=owner_profile_id,
                reason="subscription_lapsed",  # must match listing_use_cases._SUBSCRIPTION_LAPSE_REASON
                now=envelope.occurred_at,
            )


async def handle_trial_subscription_event(
    session: AsyncSession, envelope: EventEnvelope, use_cases: ListingUseCases
) -> None:
    """ADR-0010. profiles' `TrialSubscriptionStarted`/`TrialSubscriptionEnded` -- structurally
    identical to `handle_subscription_visibility_event` above (same `suspend_all_by_owner_profile`/
    `reactivate_all_by_owner_profile` calls, same lapse-reason string so
    `reactivate_all_by_owner_profile`'s "only restore what I suspended" guard works uniformly
    regardless of whether the lapse was trial- or payment-caused), but a SEPARATE handler and
    ledger key rather than reusing billing's `EntitlementActivated`/`EntitlementExpired`
    vocabulary -- profiles is not billing, and emitting an event literally named
    `EntitlementActivated` for a trial (which is not a billing `Entitlement` at all, see
    ADR-0010) would misdescribe its own producer, the same "one handler per producer+concern"
    discipline this module already applies to `handle_entitlement_event` vs.
    `handle_listing_promotion_event` vs. `handle_subscription_visibility_event`."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_TRIAL_SUBSCRIPTION_HANDLER,
    ) as is_fresh:
        if not is_fresh:
            return
        owner_profile_id_raw = envelope.payload.get("ownerProfileId")
        if owner_profile_id_raw is None:
            return
        owner_profile_id = BusinessProfileId(value=UUID(str(owner_profile_id_raw)))
        if envelope.event_type == "TrialSubscriptionStarted":
            await use_cases.reactivate_all_by_owner_profile(
                owner_profile_id=owner_profile_id, now=envelope.occurred_at
            )
        else:
            await use_cases.suspend_all_by_owner_profile(
                owner_profile_id=owner_profile_id,
                reason="subscription_lapsed",  # must match listing_use_cases._SUBSCRIPTION_LAPSE_REASON
                now=envelope.occurred_at,
            )


async def handle_identity_event(
    session: AsyncSession, envelope: EventEnvelope, use_cases: ListingUseCases
) -> None:
    """DB Architecture Sec 14.4: "account suspension -> listings hidden by catalog's own
    transition" -- catalog reacts to identity's own `AccountSuspended` event (never a static
    import of identity; the fact arrives via the outbox, X-04 style) by suspending every
    currently-visible listing that account owns, through `ListingUseCases.suspend_all_by_owner`
    (the SAME domain transition -- `Listing.suspend()` -- an owner-invoked `changeListingStatus`
    would use, just triggered by this reaction instead of a request). Unlike `handle_media_event`'s
    narrow, repository-only path, this needs the real business rule (`suspend_all_by_owner`
    itself, which iterates pages and publishes one `ListingSuspended` per listing) -- routed
    through `ListingUseCases`, not reimplemented here."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_IDENTITY_HANDLER,
    ) as is_fresh:
        if not is_fresh:
            return
        if envelope.event_type != "AccountSuspended":
            return
        account_id = envelope.payload.get("accountId")
        if account_id is None:
            return
        reason = envelope.payload.get("reason")
        await use_cases.suspend_all_by_owner(
            owner_user_id=UserId(value=UUID(str(account_id))),
            reason=f"account suspended: {reason}" if reason else "account suspended",
            now=envelope.occurred_at,
        )
