"""Idempotent projection handlers for the event streams ads consumes but never statically imports
the producer of (I-08-style ACL, X-06): billing's `EntitlementActivated`/`Expired`/`Revoked`
(`BANNER_SLOT_BOOKING` entitlement projection, I-15/I-21) and media's `MediaAssetReady`/
`MediaAssetRejected` (creative scan-status projection, I-20).

`handle_entitlement_event` is wired live (`composition_root.make_billing_entitlement_fanout_
handler`'s fourth route, added by this task the same way Task P-13 added notifications as the
third route onto that SAME dispatcher -- billing's `outbox_event` table can only be safely
drained by one `OutboxDispatcher` instance).

`handle_media_event` is built and unit-tested but NOT wired to a live dispatcher against media's
own outbox in this task -- `catalog`'s and `profiles`' own equivalent handlers are already,
identically, unwired pre-existing known gaps (`catalog/README.md`/composition_root.py's own
`make_profiles_media_status_projection_handler` docstring: media's `outbox_event` table can only
be safely drained by ONE `OutboxDispatcher`, and building the multi-consumer fan-out mechanism a
third independent consumer would need is a bigger structural change than this task's own scope
(ad-serving/banners) -- flagged here and in `ads/README.md` "Known gaps" rather than silently
building a competing, racing dispatcher (AIR-01: not this task's to fix).

Handlers are plain functions taking an already-open `AsyncSession` and a `shared_kernel.
EventEnvelope`, matching `backbone.outbox.dispatcher.EventHandler`'s shape.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ads.application.ports import EntitlementSnapshot
from ads.domain import CreativeStatus
from ads.infrastructure.persistence.models import ProcessedEventRow
from ads.infrastructure.persistence.repository import (
    SqlalchemyBannerCampaignRepository,
    SqlalchemyEntitlementProjectionRepository,
)
from backbone.idempotency import idempotent_consume
from shared_kernel import EventEnvelope

_ENTITLEMENT_HANDLER = "ads.billing_entitlement_projection"
_MEDIA_HANDLER = "ads.media_creative_status_projection"

_RELEVANT_ENTITLEMENT_TYPES = {"BANNER_SLOT_BOOKING"}

_MEDIA_STATUS_BY_EVENT_TYPE = {
    "MediaAssetReady": CreativeStatus.CLEAN,
    "MediaAssetRejected": CreativeStatus.QUARANTINED,
}


async def handle_entitlement_event(session: AsyncSession, envelope: EventEnvelope) -> None:
    """I-15/I-21: projects billing's own `BANNER_SLOT_BOOKING` entitlement events into ads'
    local `entitlement_projection` table. The composition root's own fanout handler only routes
    events whose `payload["entitlementType"] == "BANNER_SLOT_BOOKING"` here (mirroring how it
    already filters `ACTIVE_SUBSCRIPTION` to catalog and `VERIFICATION_ELIGIBILITY` to profiles)
    -- this handler re-checks the same filter defensively rather than trusting the caller."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_ENTITLEMENT_HANDLER,
    ) as is_fresh:
        if not is_fresh:
            return
        payload = envelope.payload
        if payload.get("entitlementType") not in _RELEVANT_ENTITLEMENT_TYPES:
            return
        entitlement_id_raw = payload.get("entitlementId")
        target_id_raw = payload.get("targetId")
        if entitlement_id_raw is None or target_id_raw is None:
            return
        entitlement_id = UUID(str(entitlement_id_raw))
        projection = SqlalchemyEntitlementProjectionRepository(session)

        if envelope.event_type == "EntitlementActivated":
            valid_from_raw = payload.get("validFrom")
            valid_until_raw = payload.get("validUntil")
            if valid_from_raw is None or valid_until_raw is None:
                return
            await projection.upsert(
                EntitlementSnapshot(
                    entitlement_id=entitlement_id,
                    target_id=UUID(str(target_id_raw)),
                    valid_from=datetime.fromisoformat(str(valid_from_raw)),
                    valid_until=datetime.fromisoformat(str(valid_until_raw)),
                    activation_state="ACTIVE",
                )
            )
        elif envelope.event_type == "EntitlementExpired":
            await projection.mark_state(entitlement_id, activation_state="EXPIRED")
        elif envelope.event_type == "EntitlementRevoked":
            await projection.mark_state(entitlement_id, activation_state="REVOKED")


async def handle_media_event(session: AsyncSession, envelope: EventEnvelope) -> None:
    """X-06: projects media's own scan outcome onto every `BannerCampaign` currently referencing
    this creative (`BannerCampaign.mark_creative_status`'s own always-applicable, redelivery-safe
    docstring). NOT wired to a live dispatcher in this task -- see this module's own docstring."""
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler=_MEDIA_HANDLER,
    ) as is_fresh:
        if not is_fresh:
            return
        status = _MEDIA_STATUS_BY_EVENT_TYPE.get(envelope.event_type)
        if status is None:
            return
        media_asset_id_raw = envelope.payload.get("mediaAssetId")
        if media_asset_id_raw is None:
            return
        media_asset_id = UUID(str(media_asset_id_raw))
        campaigns = SqlalchemyBannerCampaignRepository(session)
        for campaign in await campaigns.list_by_creative_media_asset_id(media_asset_id):
            updated = campaign.mark_creative_status(status, now=envelope.occurred_at)
            await campaigns.save(updated)
