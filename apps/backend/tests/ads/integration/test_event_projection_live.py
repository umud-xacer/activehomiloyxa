"""Integration tests: `ads.infrastructure.event_projection`'s idempotent consumers against real
PostgreSQL -- the `ProcessedEventRow` ledger + `idempotent_consume` is what actually needs a real
`INSERT ... ON CONFLICT` to prove (mirrors `apps/backend/tests/notifications/integration/
test_event_projection_live.py`'s own pattern).

`handle_entitlement_event` is wired live in `composition_root.make_billing_entitlement_fanout_
handler`'s fourth route; `handle_media_event` is built and tested here but NOT wired to a live
dispatcher against media's own outbox (see `ads/README.md` "Known gaps" -- the same pre-existing,
documented single-consumer-per-outbox-table limitation catalog's/profiles' own equivalent
handlers already have).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ads.domain import BannerCampaign, CreativeStatus, Schedule, Targeting
from ads.infrastructure.event_projection import handle_entitlement_event, handle_media_event
from ads.infrastructure.persistence.models import (
    BannerCampaignRow,
    EntitlementProjectionRow,
    ProcessedEventRow,
)
from ads.infrastructure.persistence.repository import SqlalchemyBannerCampaignRepository
from shared_kernel import EventEnvelope

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _entitlement_activated(
    *, entitlement_id: object, target_id: object, entitlement_type: str = "BANNER_SLOT_BOOKING"
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type="EntitlementActivated",
        occurred_at=NOW,
        actor=None,
        aggregate_type="Entitlement",
        aggregate_id=entitlement_id,  # type: ignore[arg-type]
        payload={
            "entitlementId": str(entitlement_id),
            "orderId": str(uuid4()),
            "entitlementType": entitlement_type,
            "ownerProfileId": str(uuid4()),
            "targetId": str(target_id),
            "listingId": None,
            "kind": None,
            "productDefinitionId": str(uuid4()),
            "quota": None,
            "validFrom": NOW.isoformat(),
            "validUntil": (NOW + timedelta(days=30)).isoformat(),
        },
    )


async def test_entitlement_activated_projects_a_banner_slot_booking_entitlement(
    db_session: AsyncSession,
) -> None:
    entitlement_id = uuid4()
    target_id = uuid4()
    envelope = _entitlement_activated(entitlement_id=entitlement_id, target_id=target_id)

    await handle_entitlement_event(db_session, envelope)
    await db_session.flush()

    row = await db_session.get(EntitlementProjectionRow, entitlement_id)
    assert row is not None
    assert row.target_id == target_id
    assert row.activation_state == "ACTIVE"


async def test_entitlement_activated_for_a_different_entitlement_type_is_ignored(
    db_session: AsyncSession,
) -> None:
    entitlement_id = uuid4()
    envelope = _entitlement_activated(
        entitlement_id=entitlement_id, target_id=uuid4(), entitlement_type="ACTIVE_SUBSCRIPTION"
    )

    await handle_entitlement_event(db_session, envelope)
    await db_session.flush()

    row = await db_session.get(EntitlementProjectionRow, entitlement_id)
    assert row is None


async def test_entitlement_expired_marks_the_projection_expired(db_session: AsyncSession) -> None:
    entitlement_id = uuid4()
    target_id = uuid4()
    await handle_entitlement_event(
        db_session, _entitlement_activated(entitlement_id=entitlement_id, target_id=target_id)
    )
    await db_session.flush()

    expired_envelope = EventEnvelope(
        event_id=uuid4(),
        event_type="EntitlementExpired",
        occurred_at=NOW,
        actor=None,
        aggregate_type="Entitlement",
        aggregate_id=entitlement_id,
        payload={
            "entitlementId": str(entitlement_id),
            "orderId": str(uuid4()),
            "entitlementType": "BANNER_SLOT_BOOKING",
            "ownerProfileId": str(uuid4()),
            "targetId": str(target_id),
            "listingId": None,
            "kind": None,
        },
    )
    await handle_entitlement_event(db_session, expired_envelope)
    await db_session.flush()

    row = await db_session.get(EntitlementProjectionRow, entitlement_id)
    assert row is not None
    assert row.activation_state == "EXPIRED"


async def test_redelivering_the_same_activation_event_projects_it_exactly_once(
    db_session: AsyncSession,
) -> None:
    entitlement_id = uuid4()
    envelope = _entitlement_activated(entitlement_id=entitlement_id, target_id=uuid4())

    await handle_entitlement_event(db_session, envelope)
    await db_session.flush()
    await handle_entitlement_event(db_session, envelope)
    await db_session.flush()

    processed = await db_session.execute(
        select(ProcessedEventRow).where(ProcessedEventRow.event_id == envelope.event_id)
    )
    assert len(processed.scalars().all()) == 1


def _campaign(**overrides: object) -> BannerCampaign:
    defaults: dict[str, object] = {
        "campaign_id": uuid4(),
        "placement_slot_id": uuid4(),
        "placement_slot_version_id": uuid4(),
        "slot_key": "HOMEPAGE_TOP",
        "creative_media_asset_id": uuid4(),
        "creative_status": CreativeStatus.PENDING,
        "entitlement_id": uuid4(),
        "schedule": Schedule(start=NOW, end=NOW + timedelta(days=8), priority=0),
        "targeting": Targeting(),
        "now": NOW,
    }
    defaults.update(overrides)
    return BannerCampaign.create(**defaults)  # type: ignore[arg-type]


def _media_event(event_type: str, media_asset_id: object) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        occurred_at=NOW,
        actor=None,
        aggregate_type="MediaAsset",
        aggregate_id=media_asset_id,  # type: ignore[arg-type]
        payload={"mediaAssetId": str(media_asset_id)},
    )


async def test_media_asset_ready_marks_referencing_campaigns_clean(
    db_session: AsyncSession,
) -> None:
    """`handle_media_event` exists and is exercised here, even though it is not wired to a live
    dispatcher in this task (see this file's own module docstring)."""
    media_asset_id = uuid4()
    campaign = _campaign(creative_media_asset_id=media_asset_id)
    repo = SqlalchemyBannerCampaignRepository(db_session)
    await repo.add(campaign)
    await db_session.flush()

    await handle_media_event(db_session, _media_event("MediaAssetReady", media_asset_id))
    await db_session.flush()

    row = await db_session.get(BannerCampaignRow, campaign.id)
    assert row is not None
    assert row.creative_status == "CLEAN"


async def test_media_asset_rejected_marks_referencing_campaigns_quarantined(
    db_session: AsyncSession,
) -> None:
    media_asset_id = uuid4()
    campaign = _campaign(
        creative_media_asset_id=media_asset_id, creative_status=CreativeStatus.CLEAN
    )
    repo = SqlalchemyBannerCampaignRepository(db_session)
    await repo.add(campaign)
    await db_session.flush()

    await handle_media_event(db_session, _media_event("MediaAssetRejected", media_asset_id))
    await db_session.flush()

    row = await db_session.get(BannerCampaignRow, campaign.id)
    assert row is not None
    assert row.creative_status == "QUARANTINED"


async def test_media_event_for_an_unreferenced_asset_touches_no_campaign(
    db_session: AsyncSession,
) -> None:
    campaign = _campaign()
    repo = SqlalchemyBannerCampaignRepository(db_session)
    await repo.add(campaign)
    await db_session.flush()

    await handle_media_event(db_session, _media_event("MediaAssetReady", uuid4()))
    await db_session.flush()

    row = await db_session.get(BannerCampaignRow, campaign.id)
    assert row is not None
    assert row.creative_status == "PENDING"  # untouched
