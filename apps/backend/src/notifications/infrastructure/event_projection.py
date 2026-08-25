"""Idempotent projection handlers for the 24-event `EventKey` subset notifications consumes
(mechanically derived from `contracts/events/*.py`'s own frozen "Principal consumers: ...
Notifications ..." docstrings -- DDD Sec 6's own authoritative event catalogue; the cited DDD
Sec 8.8 does not exist as a section in the current document, so this is the code-verifiable
anchor, confirmed with the repository owner). One function per emitting module, mirroring
`moderation.infrastructure.event_projection`'s own style: each wraps `backbone.idempotency.
idempotent_consume` against this module's own `ProcessedEventRow` ledger, keyed on the
*producing* event's own `event_id` plus a handler name unique to this consumer -- redelivery of
the same event is a no-op, never a duplicate notification (the module's own most user-visible
invariant).

Every handler resolves a `RecipientSnapshot` via `RecipientDirectoryPort` (the composition-root-
only bridge -- see `application/ports.py`'s own docstring for why notifications cannot import
identity/profiles/catalog/billing directly) THEN calls `NotificationDispatchUseCases.
queue_for_event`, which is a no-op if no recipient could be resolved or no template/preference
allows delivery. Returns the list of freshly `QUEUED` dispatches for the caller (a
composition-root `EventHandler` closure) to actually dispatch AFTER this function's own
transaction commits (Playbook Sec 6: "a transaction is never held open across a provider port
call") -- this file only ever writes rows, it never calls a channel provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from backbone.idempotency import idempotent_consume
from notifications.application import QueuedDispatch
from notifications.infrastructure.persistence.models import ProcessedEventRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from notifications.application import (
        NotificationDispatchUseCases,
        OrderRecipientProjectionRepository,
        RecipientDirectoryPort,
    )
    from shared_kernel import EventEnvelope

_IDENTITY_HANDLER = "notifications.identity_projection"
_PROFILES_HANDLER = "notifications.profiles_projection"
_CATALOG_HANDLER = "notifications.catalog_projection"
_BILLING_HANDLER = "notifications.billing_projection"
_ADS_HANDLER = "notifications.ads_projection"
_MESSAGING_HANDLER = "notifications.messaging_projection"
_MODERATION_HANDLER = "notifications.moderation_projection"

_IDENTITY_EVENT_TYPES = {"UserRegistered", "AccountSuspended", "AccountClosed"}
_PROFILES_EVENT_TYPES = {
    "VerificationRequested",
    "BusinessVerified",
    "VerificationRejected",
    "VerifiedBadgeExpired",
}
_CATALOG_EVENT_TYPES = {
    "ListingPublished",
    "ListingSuspended",
    "ListingArchived",
    "ListingDeleted",
    "ListingExpired",
    "ListingRenewed",
    "ListingSold",
}
_BILLING_PROFILE_EVENT_TYPES = {
    "OrderPlaced",
    "PaymentConfirmed",
    "EntitlementExpired",
    "EntitlementRevoked",
}
_ADS_EVENT_TYPES = {
    "BannerCampaignScheduled",
    "BannerCampaignStarted",
    "BannerCampaignEnded",
}
_MESSAGING_EVENT_TYPES = {"ChatInitiated", "MessageSent"}


async def handle_identity_event(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    use_cases: NotificationDispatchUseCases,
    recipients: RecipientDirectoryPort,
) -> list[QueuedDispatch]:
    """`UserRegistered`/`AccountSuspended`/`AccountClosed` -- the event's own `aggregate_id` IS
    the recipient's `UserId` directly (no bridge resolution needed)."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_IDENTITY_HANDLER,
    ) as is_fresh:
        if not is_fresh or envelope.event_type not in _IDENTITY_EVENT_TYPES:
            return []
        recipient = await recipients.resolve_recipient(envelope.aggregate_id)
        return await use_cases.queue_for_event(
            event_key=envelope.event_type, recipient=recipient, now=envelope.occurred_at
        )


async def handle_profiles_event(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    use_cases: NotificationDispatchUseCases,
    recipients: RecipientDirectoryPort,
) -> list[QueuedDispatch]:
    """`VerificationRequested`/`BusinessVerified`/`VerificationRejected`/`VerifiedBadgeExpired` --
    the payload names a `businessProfileId`, never the owner's `UserId` directly; resolved via
    the profile-owner bridge."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_PROFILES_HANDLER,
    ) as is_fresh:
        if not is_fresh or envelope.event_type not in _PROFILES_EVENT_TYPES:
            return []
        profile_id_raw = envelope.payload.get("businessProfileId")
        if profile_id_raw is None:
            return []
        recipient = await recipients.resolve_recipient_for_profile(UUID(str(profile_id_raw)))
        return await use_cases.queue_for_event(
            event_key=envelope.event_type, recipient=recipient, now=envelope.occurred_at
        )


async def handle_catalog_event(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    use_cases: NotificationDispatchUseCases,
    recipients: RecipientDirectoryPort,
) -> list[QueuedDispatch]:
    """`ListingPublished`/`Suspended`/`Archived`/`Deleted`/`Expired`/`Renewed`/`Sold` -- catalog's
    own `_listing_payload` already carries `ownerUserId` directly."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_CATALOG_HANDLER
    ) as is_fresh:
        if not is_fresh or envelope.event_type not in _CATALOG_EVENT_TYPES:
            return []
        owner_user_id_raw = envelope.payload.get("ownerUserId")
        if owner_user_id_raw is None:
            return []
        recipient = await recipients.resolve_recipient(UUID(str(owner_user_id_raw)))
        return await use_cases.queue_for_event(
            event_key=envelope.event_type, recipient=recipient, now=envelope.occurred_at
        )


async def handle_billing_event(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    use_cases: NotificationDispatchUseCases,
    recipients: RecipientDirectoryPort,
    order_projection: OrderRecipientProjectionRepository,
) -> list[QueuedDispatch]:
    """`OrderPlaced`/`PaymentConfirmed`/`EntitlementExpired`/`EntitlementRevoked` each carry a
    `purchaserProfileId`/`ownerProfileId` directly -- resolved via the profile-owner bridge.
    `InvoiceIssued`'s own payload carries NEITHER (only `invoiceId`/`orderId`/`invoiceNumber`/
    `amount`/`currency`/`status`) -- resolved instead via the local `order_recipient_projection`
    this same handler populates when it sees that order's own `OrderPlaced` event moments
    earlier (both events are published in the same `OrderUseCases.place_order` call, so
    `OrderPlaced` always precedes `InvoiceIssued` in commit order on billing's own outbox)."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_BILLING_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return []
        if envelope.event_type == "OrderPlaced":
            profile_id_raw = envelope.payload.get("purchaserProfileId")
            if profile_id_raw is None:
                return []
            profile_id = UUID(str(profile_id_raw))
            order_id_raw = envelope.payload.get("orderId")
            if order_id_raw is not None:
                await order_projection.upsert(
                    order_id=UUID(str(order_id_raw)), purchaser_profile_id=profile_id
                )
            recipient = await recipients.resolve_recipient_for_profile(profile_id)
            return await use_cases.queue_for_event(
                event_key=envelope.event_type,
                recipient=recipient,
                now=envelope.occurred_at,
            )
        if envelope.event_type == "InvoiceIssued":
            order_id_raw = envelope.payload.get("orderId")
            if order_id_raw is None:
                return []
            invoice_profile_id = await order_projection.get_purchaser_profile_id(
                UUID(str(order_id_raw))
            )
            if invoice_profile_id is None:
                return []
            recipient = await recipients.resolve_recipient_for_profile(invoice_profile_id)
            return await use_cases.queue_for_event(
                event_key=envelope.event_type,
                recipient=recipient,
                now=envelope.occurred_at,
            )
        if envelope.event_type in _BILLING_PROFILE_EVENT_TYPES:
            profile_id_raw = envelope.payload.get("purchaserProfileId") or envelope.payload.get(
                "ownerProfileId"
            )
            if profile_id_raw is None:
                return []
            recipient = await recipients.resolve_recipient_for_profile(UUID(str(profile_id_raw)))
            return await use_cases.queue_for_event(
                event_key=envelope.event_type,
                recipient=recipient,
                now=envelope.occurred_at,
            )
        return []


async def handle_ads_event(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    use_cases: NotificationDispatchUseCases,
    recipients: RecipientDirectoryPort,
) -> list[QueuedDispatch]:
    """`BannerCampaignScheduled`/`Started`/`Ended` -- `ads` (BC-09) is still an `interfaces/`-only
    stub (no real aggregate, no outbox, never publishes a real event), so this handler's own
    payload-field assumption (`bookingProfileId`, the natural analogue of billing's
    `ownerProfileId` for an ad-serving entitlement booking) is UNVERIFIED against real ads code
    and is exercised only via synthetic `EventEnvelope`s in tests -- see README "Known gaps"."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_ADS_HANDLER
    ) as is_fresh:
        if not is_fresh or envelope.event_type not in _ADS_EVENT_TYPES:
            return []
        profile_id_raw = envelope.payload.get("bookingProfileId")
        if profile_id_raw is None:
            return []
        recipient = await recipients.resolve_recipient_for_profile(UUID(str(profile_id_raw)))
        return await use_cases.queue_for_event(
            event_key=envelope.event_type, recipient=recipient, now=envelope.occurred_at
        )


async def handle_messaging_event(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    use_cases: NotificationDispatchUseCases,
    recipients: RecipientDirectoryPort,
) -> list[QueuedDispatch]:
    """`ChatInitiated`/`MessageSent` -- messaging's own payload already carries
    `recipientUserId` directly (the OTHER conversation participant, never the actor)."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_MESSAGING_HANDLER,
    ) as is_fresh:
        if not is_fresh or envelope.event_type not in _MESSAGING_EVENT_TYPES:
            return []
        recipient_user_id_raw = envelope.payload.get("recipientUserId")
        if recipient_user_id_raw is None:
            return []
        recipient = await recipients.resolve_recipient(UUID(str(recipient_user_id_raw)))
        return await use_cases.queue_for_event(
            event_key=envelope.event_type, recipient=recipient, now=envelope.occurred_at
        )


async def handle_moderation_event(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    use_cases: NotificationDispatchUseCases,
    recipients: RecipientDirectoryPort,
) -> list[QueuedDispatch]:
    """`ModerationActionTaken` -- the "affected user" (DDD Sec 6's own consumer note) depends on
    `subjectType`: `USER` names the `UserId` directly; `PROFILE`/`LISTING` need the owner-
    resolution bridge; `CONVERSATION` has no reliable single "affected user" id anywhere in the
    payload chain (a conversation has two participants and this event's own payload never named
    which one), so it is skipped -- documented in README "Known gaps", not guessed at."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_MODERATION_HANDLER,
    ) as is_fresh:
        if not is_fresh or envelope.event_type != "ModerationActionTaken":
            return []
        subject_type = envelope.payload.get("subjectType")
        subject_id_raw = envelope.payload.get("subjectId")
        if subject_type is None or subject_id_raw is None:
            return []
        subject_id = UUID(str(subject_id_raw))
        if subject_type == "USER":
            recipient = await recipients.resolve_recipient(subject_id)
        elif subject_type == "PROFILE":
            recipient = await recipients.resolve_recipient_for_profile(subject_id)
        elif subject_type == "LISTING":
            recipient = await recipients.resolve_recipient_for_listing(subject_id)
        else:
            return []
        return await use_cases.queue_for_event(
            event_key=envelope.event_type, recipient=recipient, now=envelope.occurred_at
        )
