"""Idempotent projection handlers for the two event streams profiles consumes but never imports
the producer of (I-12/X-06): billing's entitlement events (`VerificationEligibility` projection)
and media's `MediaAssetRejected` (portfolio/document cleanliness projection). Mirrors
`catalog.infrastructure.event_projection`'s style exactly.

Each handler wraps `backbone.idempotency.consumer.idempotent_consume` against profiles' own
`ProcessedEventRow` ledger, keyed on the *producing* event's own `event_id` -- redelivery of the
same event is a no-op, never a duplicate side effect. Handlers are plain functions taking an
already-open `AsyncSession` and a `shared_kernel.EventEnvelope`, matching `backbone.outbox.
dispatcher.EventHandler`'s shape exactly (once wrapped by the composition root the same way
`catalog.infrastructure.event_projection.handle_entitlement_event`'s own docstring documents --
wiring one module's outbox to another module's consumer is composition-root work by construction).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from backbone.idempotency import idempotent_consume
from profiles.application import ProfileUseCases, VerificationUseCases
from profiles.application.ports import (
    SubscriptionEligibilitySnapshot,
    VerificationEligibilitySnapshot,
)
from profiles.infrastructure.persistence import ProcessedEventRow
from shared_kernel import BusinessProfileId

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from shared_kernel import EventEnvelope

_ENTITLEMENT_HANDLER = "profiles.verification_entitlement_projection"
_SUBSCRIPTION_HANDLER = "profiles.subscription_entitlement_projection"
_MEDIA_STATUS_HANDLER = "profiles.media_asset_status_projection"

_ACTIVATION_STATE_BY_EVENT_TYPE = {
    "EntitlementActivated": "ACTIVE",
    "EntitlementExpired": "EXPIRED",
    "EntitlementRevoked": "REVOKED",
}
_RELEVANT_ENTITLEMENT_TYPE = "VERIFICATION_ELIGIBILITY"
_RELEVANT_SUBSCRIPTION_TYPE = "ACTIVE_SUBSCRIPTION"


async def handle_entitlement_event(
    session: AsyncSession, envelope: EventEnvelope, use_cases: VerificationUseCases
) -> None:
    """I-12: projects a billing entitlement event into `profiles.
    verification_entitlement_projection` -- profiles never imports billing (SAD Sec 8.1); this is
    the async, outbox-driven, one-way read side of X-03. Only `VERIFICATION_ELIGIBILITY`
    entitlements are relevant (mirrors `catalog.infrastructure.event_projection.
    handle_entitlement_event`'s own `entitlementType` discrimination for `ACTIVE_SUBSCRIPTION`) --
    the composition root's routing already filters by event type before calling this, but the
    `entitlementType` payload field is re-checked here too (defence in depth, same reasoning
    catalog's own handler documents)."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_ENTITLEMENT_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        activation_state = _ACTIVATION_STATE_BY_EVENT_TYPE.get(envelope.event_type)
        if activation_state is None:
            return
        payload = envelope.payload
        if payload.get("entitlementType") != _RELEVANT_ENTITLEMENT_TYPE:
            return
        owner_profile_id = payload.get("ownerProfileId") or payload.get("targetId")
        entitlement_id = payload.get("entitlementId")
        valid_from_raw = payload.get("validFrom")
        valid_until_raw = payload.get("validUntil")
        if owner_profile_id is None or entitlement_id is None or valid_until_raw is None:
            return
        snapshot = VerificationEligibilitySnapshot(
            entitlement_id=_as_uuid(entitlement_id),
            business_profile_id=BusinessProfileId(value=_as_uuid(owner_profile_id)),
            valid_from=(
                datetime.fromisoformat(str(valid_from_raw))
                if valid_from_raw
                else envelope.occurred_at
            ),
            valid_until=datetime.fromisoformat(str(valid_until_raw)),
            activation_state=activation_state,  # type: ignore[arg-type]
            source_event_id=envelope.event_id,
        )
        await use_cases.apply_entitlement_projection(snapshot)


async def handle_subscription_entitlement_event(
    session: AsyncSession, envelope: EventEnvelope, use_cases: ProfileUseCases
) -> None:
    """Monetization task: the `ACTIVE_SUBSCRIPTION` slice of billing's `EntitlementActivated`/
    `EntitlementExpired`/`EntitlementRevoked`, projected into `profiles.
    subscription_entitlement_projection` -- mirrors `handle_entitlement_event` above almost
    exactly (same event-type/entitlement-type discrimination shape), just landing in
    `ProfileUseCases.apply_subscription_projection` instead of `VerificationUseCases.
    apply_entitlement_projection` (a different projection table, a different consumer: the
    landing page's own subscription-status read, not verification eligibility)."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_SUBSCRIPTION_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        activation_state = _ACTIVATION_STATE_BY_EVENT_TYPE.get(envelope.event_type)
        if activation_state is None:
            return
        payload = envelope.payload
        if payload.get("entitlementType") != _RELEVANT_SUBSCRIPTION_TYPE:
            return
        owner_profile_id = payload.get("ownerProfileId") or payload.get("targetId")
        entitlement_id = payload.get("entitlementId")
        valid_from_raw = payload.get("validFrom")
        valid_until_raw = payload.get("validUntil")
        if owner_profile_id is None or entitlement_id is None or valid_until_raw is None:
            return
        snapshot = SubscriptionEligibilitySnapshot(
            business_profile_id=BusinessProfileId(value=_as_uuid(owner_profile_id)),
            entitlement_id=_as_uuid(entitlement_id),
            valid_from=(
                datetime.fromisoformat(str(valid_from_raw))
                if valid_from_raw
                else envelope.occurred_at
            ),
            valid_until=datetime.fromisoformat(str(valid_until_raw)),
            activation_state=activation_state,  # type: ignore[arg-type]
            source_event_id=envelope.event_id,
        )
        await use_cases.apply_subscription_projection(snapshot)


async def handle_media_event(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    profiles: ProfileUseCases,
    verifications: VerificationUseCases,
) -> None:
    """X-06: `MediaAssetRejected` removes the referencing portfolio item or submitted document
    (Physical DB's `portfolio_item`/`submitted_document` carry no status column to flip -- see
    `profiles.domain.portfolio_item.PortfolioItem`'s own docstring). `MediaAssetAccepted`/
    `MediaAssetReady` need no handler here: neither child entity has a status field to advance."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_MEDIA_STATUS_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        if envelope.event_type != "MediaAssetRejected":
            return
        media_asset_id = payload_uuid(envelope.payload, "mediaAssetId")
        if media_asset_id is None:
            return
        await profiles.apply_portfolio_media_rejection(media_asset_id, now=envelope.occurred_at)
        await verifications.apply_document_media_rejection(media_asset_id, now=envelope.occurred_at)


def payload_uuid(payload: dict[str, object], field: str) -> UUID | None:
    value = payload.get(field)
    return UUID(str(value)) if value is not None else None


def _as_uuid(value: object) -> UUID:
    return UUID(str(value))
