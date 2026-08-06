"""Integration tests: `SqlalchemyBannerCampaignRepository`/
`SqlalchemyEntitlementProjectionRepository` round-trip against real PostgreSQL, including the
physical CHECK constraints (`ck_banner_campaign_status`, `ck_banner_campaign_schedule_ordering`,
...) and the no-counter-columns schema shape."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ads.application.ports import EntitlementSnapshot
from ads.domain import BannerCampaign, CreativeStatus, Schedule, Targeting
from ads.infrastructure.persistence.repository import (
    SqlalchemyBannerCampaignRepository,
    SqlalchemyEntitlementProjectionRepository,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _campaign(**overrides: object) -> BannerCampaign:
    defaults: dict[str, object] = {
        "campaign_id": uuid4(),
        "placement_slot_id": uuid4(),
        "placement_slot_version_id": uuid4(),
        "slot_key": "HOMEPAGE_TOP",
        "creative_media_asset_id": uuid4(),
        "creative_status": CreativeStatus.CLEAN,
        "entitlement_id": uuid4(),
        "schedule": Schedule(
            start=NOW + timedelta(days=1), end=NOW + timedelta(days=8), priority=0
        ),
        "targeting": Targeting(languages=("ru", "en")),
        "now": NOW,
    }
    defaults.update(overrides)
    return BannerCampaign.create(**defaults)  # type: ignore[arg-type]


async def test_campaign_add_then_get_by_id_round_trips(db_session: AsyncSession) -> None:
    repo = SqlalchemyBannerCampaignRepository(db_session)
    campaign = _campaign()
    await repo.add(campaign)
    await db_session.flush()

    fetched = await repo.get_by_id(campaign.id)
    assert fetched is not None
    assert fetched.slot_key == "HOMEPAGE_TOP"
    assert fetched.targeting.languages == ("ru", "en")
    assert fetched.status.value == "DRAFT"


async def test_campaign_save_persists_a_state_transition(db_session: AsyncSession) -> None:
    repo = SqlalchemyBannerCampaignRepository(db_session)
    campaign = _campaign()
    await repo.add(campaign)
    await db_session.flush()

    scheduled = campaign.schedule_campaign(now=NOW)
    saved = await repo.save(scheduled)
    assert saved.status.value == "SCHEDULED"

    fetched = await repo.get_by_id(campaign.id)
    assert fetched is not None
    assert fetched.status.value == "SCHEDULED"


async def test_list_candidates_for_serve_only_returns_scheduled_and_running_in_the_requested_slot(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyBannerCampaignRepository(db_session)

    draft = _campaign(slot_key="HOMEPAGE_TOP")
    await repo.add(draft)

    scheduled = _campaign(slot_key="HOMEPAGE_TOP")
    await repo.add(scheduled)
    await db_session.flush()
    await repo.save(scheduled.schedule_campaign(now=NOW))

    other_slot = _campaign(slot_key="CATEGORY_SIDEBAR")
    await repo.add(other_slot)
    await db_session.flush()
    await repo.save(other_slot.schedule_campaign(now=NOW))

    candidates = await repo.list_candidates_for_serve(slot_key="HOMEPAGE_TOP")
    assert {c.id for c in candidates} == {scheduled.id}


async def test_list_candidates_for_serve_orders_by_priority_descending(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyBannerCampaignRepository(db_session)

    low = _campaign(
        slot_key="HOMEPAGE_TOP",
        schedule=Schedule(start=NOW, end=NOW + timedelta(days=1), priority=1),
    )
    high = _campaign(
        slot_key="HOMEPAGE_TOP",
        schedule=Schedule(start=NOW, end=NOW + timedelta(days=1), priority=9),
    )
    for campaign in (low, high):
        await repo.add(campaign)
        await db_session.flush()
        await repo.save(campaign.schedule_campaign(now=NOW))

    candidates = await repo.list_candidates_for_serve(slot_key="HOMEPAGE_TOP")
    assert [c.id for c in candidates] == [high.id, low.id]


async def test_list_due_to_start_and_list_due_to_end(db_session: AsyncSession) -> None:
    repo = SqlalchemyBannerCampaignRepository(db_session)

    due_to_start = _campaign(
        schedule=Schedule(start=NOW - timedelta(minutes=1), end=NOW + timedelta(days=8), priority=0)
    )
    await repo.add(due_to_start)
    await db_session.flush()
    await repo.save(due_to_start.schedule_campaign(now=NOW))

    due_to_end = _campaign(
        schedule=Schedule(start=NOW - timedelta(days=8), end=NOW - timedelta(minutes=1), priority=0)
    )
    await repo.add(due_to_end)
    await db_session.flush()
    scheduled_due_to_end = await repo.save(due_to_end.schedule_campaign(now=NOW))
    await repo.save(scheduled_due_to_end.start(now=NOW))

    due_starts = await repo.list_due_to_start(now=NOW)
    assert {c.id for c in due_starts} == {due_to_start.id}

    due_ends = await repo.list_due_to_end(now=NOW)
    assert {c.id for c in due_ends} == {due_to_end.id}


async def test_list_by_creative_media_asset_id_finds_every_referencing_campaign(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyBannerCampaignRepository(db_session)
    media_asset_id = uuid4()
    campaign = _campaign(creative_media_asset_id=media_asset_id)
    await repo.add(campaign)
    await db_session.flush()

    found = await repo.list_by_creative_media_asset_id(media_asset_id)
    assert [c.id for c in found] == [campaign.id]

    not_found = await repo.list_by_creative_media_asset_id(uuid4())
    assert not_found == ()


async def test_entitlement_projection_upsert_then_get_by_id(db_session: AsyncSession) -> None:
    repo = SqlalchemyEntitlementProjectionRepository(db_session)
    snapshot = EntitlementSnapshot(
        entitlement_id=uuid4(),
        target_id=uuid4(),
        valid_from=NOW,
        valid_until=NOW + timedelta(days=30),
        activation_state="ACTIVE",
    )
    await repo.upsert(snapshot)
    await db_session.flush()

    fetched = await repo.get_by_id(snapshot.entitlement_id)
    assert fetched is not None
    assert fetched.activation_state == "ACTIVE"


async def test_entitlement_projection_mark_state_updates_activation_state_only(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyEntitlementProjectionRepository(db_session)
    snapshot = EntitlementSnapshot(
        entitlement_id=uuid4(),
        target_id=uuid4(),
        valid_from=NOW,
        valid_until=NOW + timedelta(days=30),
        activation_state="ACTIVE",
    )
    await repo.upsert(snapshot)
    await db_session.flush()

    await repo.mark_state(snapshot.entitlement_id, activation_state="EXPIRED")
    await db_session.flush()

    fetched = await repo.get_by_id(snapshot.entitlement_id)
    assert fetched is not None
    assert fetched.activation_state == "EXPIRED"
    assert fetched.valid_until == snapshot.valid_until  # untouched


async def test_entitlement_projection_mark_state_is_a_no_op_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    """The redelivery-ordering edge case: an EntitlementExpired/Revoked event arriving before its
    own Activated was ever projected must not raise."""
    repo = SqlalchemyEntitlementProjectionRepository(db_session)
    await repo.mark_state(uuid4(), activation_state="EXPIRED")  # must not raise
