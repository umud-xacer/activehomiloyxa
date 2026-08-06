"""Unit tests for `CampaignUseCases` (operator campaign management, FR-BANNER-002/003)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from ads.application.campaign_use_cases import CampaignUseCases
from ads.application.exceptions import (
    CampaignNotFoundError,
    EntitlementNotFoundError,
    SlotNotFoundError,
)
from ads.application.ports import EntitlementSnapshot
from ads.domain import CampaignNotEligibleError, CampaignStatus, CreativeStatus, Targeting

from .conftest import (
    FakeBannerCampaignRepository,
    FakeCreativeReaderPort,
    FakeEntitlementProjectionRepository,
    FakeOutbox,
    FakePlacementSlotReaderPort,
)

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _use_cases(
    campaigns: FakeBannerCampaignRepository,
    slots: FakePlacementSlotReaderPort,
    creatives: FakeCreativeReaderPort,
    entitlements: FakeEntitlementProjectionRepository,
    outbox: FakeOutbox,
) -> CampaignUseCases:
    return CampaignUseCases(
        campaigns=campaigns,
        slots=slots,
        creatives=creatives,
        entitlements=entitlements,
        outbox=outbox,
    )


async def _create_active_entitlement(
    entitlements: FakeEntitlementProjectionRepository, *, target_id: UUID
) -> UUID:
    entitlement_id = uuid4()
    await entitlements.upsert(
        EntitlementSnapshot(
            entitlement_id=entitlement_id,
            target_id=target_id,
            valid_from=_NOW - timedelta(days=1),
            valid_until=_NOW + timedelta(days=30),
            activation_state="ACTIVE",
        )
    )
    return entitlement_id


@pytest.mark.asyncio
async def test_create_campaign_resolves_slot_and_creative_status(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    slot = fake_slots.seed("HOMEPAGE_TOP")
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    campaign = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        entitlement_id=uuid4(),
        schedule_start=_NOW + timedelta(days=1),
        schedule_end=_NOW + timedelta(days=8),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    assert campaign.status is CampaignStatus.DRAFT
    assert campaign.placement_slot_id == slot.head_id
    assert campaign.creative_status is CreativeStatus.CLEAN  # fake_creatives' default


@pytest.mark.asyncio
async def test_create_campaign_raises_when_slot_is_unknown(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    with pytest.raises(SlotNotFoundError):
        await use_cases.create_campaign(
            slot_key="NO_SUCH_SLOT",
            creative_media_asset_id=uuid4(),
            entitlement_id=uuid4(),
            schedule_start=_NOW + timedelta(days=1),
            schedule_end=_NOW + timedelta(days=8),
            priority=0,
            targeting=Targeting(),
            operator_account_id=uuid4(),
            now=_NOW,
        )


@pytest.mark.asyncio
async def test_get_campaign_raises_not_found_for_unknown_id(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    with pytest.raises(CampaignNotFoundError):
        await use_cases.get_campaign(uuid4())


@pytest.mark.asyncio
async def test_schedule_campaign_succeeds_when_entitlement_active_and_creative_clean(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    slot = fake_slots.seed("HOMEPAGE_TOP")
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    entitlement_id = await _create_active_entitlement(
        fake_entitlement_projection, target_id=slot.head_id
    )
    campaign = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        entitlement_id=entitlement_id,
        schedule_start=_NOW + timedelta(days=1),
        schedule_end=_NOW + timedelta(days=8),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    scheduled = await use_cases.schedule_campaign(
        campaign.id, operator_account_id=uuid4(), now=_NOW
    )
    assert scheduled.status is CampaignStatus.SCHEDULED
    assert len(fake_outbox.events) == 1
    assert fake_outbox.events[0].event_type == "BannerCampaignScheduled"


@pytest.mark.asyncio
async def test_schedule_campaign_raises_when_entitlement_is_not_active(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    slot = fake_slots.seed("HOMEPAGE_TOP")
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    entitlement_id = uuid4()
    await fake_entitlement_projection.upsert(
        EntitlementSnapshot(
            entitlement_id=entitlement_id,
            target_id=slot.head_id,
            valid_from=_NOW - timedelta(days=30),
            valid_until=_NOW - timedelta(days=1),
            activation_state="EXPIRED",
        )
    )
    campaign = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        entitlement_id=entitlement_id,
        schedule_start=_NOW + timedelta(days=1),
        schedule_end=_NOW + timedelta(days=8),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    with pytest.raises(CampaignNotEligibleError):
        await use_cases.schedule_campaign(campaign.id, operator_account_id=uuid4(), now=_NOW)
    assert len(fake_outbox.events) == 0


@pytest.mark.asyncio
async def test_schedule_campaign_raises_when_entitlement_is_unknown(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    fake_slots.seed("HOMEPAGE_TOP")
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    campaign = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        entitlement_id=uuid4(),
        schedule_start=_NOW + timedelta(days=1),
        schedule_end=_NOW + timedelta(days=8),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    with pytest.raises(EntitlementNotFoundError):
        await use_cases.schedule_campaign(campaign.id, operator_account_id=uuid4(), now=_NOW)


@pytest.mark.asyncio
async def test_schedule_campaign_raises_when_creative_is_quarantined(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    slot = fake_slots.seed("HOMEPAGE_TOP")
    creative_id = uuid4()
    fake_creatives.statuses[creative_id] = CreativeStatus.QUARANTINED
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    entitlement_id = await _create_active_entitlement(
        fake_entitlement_projection, target_id=slot.head_id
    )
    campaign = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=creative_id,
        entitlement_id=entitlement_id,
        schedule_start=_NOW + timedelta(days=1),
        schedule_end=_NOW + timedelta(days=8),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    with pytest.raises(CampaignNotEligibleError):
        await use_cases.schedule_campaign(campaign.id, operator_account_id=uuid4(), now=_NOW)


@pytest.mark.asyncio
async def test_pause_then_resume_before_schedule_start_returns_to_scheduled(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    slot = fake_slots.seed("HOMEPAGE_TOP")
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    entitlement_id = await _create_active_entitlement(
        fake_entitlement_projection, target_id=slot.head_id
    )
    campaign = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        entitlement_id=entitlement_id,
        schedule_start=_NOW + timedelta(days=1),
        schedule_end=_NOW + timedelta(days=8),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    await use_cases.schedule_campaign(campaign.id, operator_account_id=uuid4(), now=_NOW)
    paused = await use_cases.pause_campaign(campaign.id, now=_NOW)
    assert paused.status is CampaignStatus.PAUSED
    resumed = await use_cases.resume_campaign(campaign.id, now=_NOW)
    assert resumed.status is CampaignStatus.SCHEDULED
    # pause/resume emit no domain event (ADR-0004) -- only the earlier schedule_campaign did.
    assert len(fake_outbox.events) == 1


@pytest.mark.asyncio
async def test_end_campaign_emits_banner_campaign_ended(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    slot = fake_slots.seed("HOMEPAGE_TOP")
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    entitlement_id = await _create_active_entitlement(
        fake_entitlement_projection, target_id=slot.head_id
    )
    campaign = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        entitlement_id=entitlement_id,
        schedule_start=_NOW + timedelta(days=1),
        schedule_end=_NOW + timedelta(days=8),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    await use_cases.schedule_campaign(campaign.id, operator_account_id=uuid4(), now=_NOW)
    ended = await use_cases.end_campaign(campaign.id, operator_account_id=uuid4(), now=_NOW)
    assert ended.status is CampaignStatus.ENDED
    assert [e.event_type for e in fake_outbox.events] == [
        "BannerCampaignScheduled",
        "BannerCampaignEnded",
    ]


@pytest.mark.asyncio
async def test_sweep_schedule_transitions_starts_and_ends_due_campaigns(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    slot = fake_slots.seed("HOMEPAGE_TOP")
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    entitlement_id = await _create_active_entitlement(
        fake_entitlement_projection, target_id=slot.head_id
    )
    due_to_start = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        entitlement_id=entitlement_id,
        schedule_start=_NOW - timedelta(minutes=1),
        schedule_end=_NOW + timedelta(days=8),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    await use_cases.schedule_campaign(due_to_start.id, operator_account_id=uuid4(), now=_NOW)

    started, ended = await use_cases.sweep_schedule_transitions(now=_NOW)
    assert started == 1
    assert ended == 0
    refreshed = await fake_campaigns.get_by_id(due_to_start.id)
    assert refreshed is not None
    assert refreshed.status is CampaignStatus.RUNNING
    assert [e.event_type for e in fake_outbox.events] == [
        "BannerCampaignScheduled",
        "BannerCampaignStarted",
    ]


@pytest.mark.asyncio
async def test_sweep_schedule_transitions_ends_a_due_campaign(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    slot = fake_slots.seed("HOMEPAGE_TOP")
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    entitlement_id = await _create_active_entitlement(
        fake_entitlement_projection, target_id=slot.head_id
    )
    due_to_end = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        entitlement_id=entitlement_id,
        schedule_start=_NOW - timedelta(days=2),
        schedule_end=_NOW - timedelta(minutes=1),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    await use_cases.schedule_campaign(due_to_end.id, operator_account_id=uuid4(), now=_NOW)
    # PAUSED (not SCHEDULED) so the sweep's `list_due_to_start` half does not also pick it up --
    # isolates this test to exercising only the "ends a due campaign" branch.
    await use_cases.pause_campaign(due_to_end.id, now=_NOW)

    started, ended = await use_cases.sweep_schedule_transitions(now=_NOW)
    assert started == 0
    assert ended == 1
    refreshed = await fake_campaigns.get_by_id(due_to_end.id)
    assert refreshed is not None
    assert refreshed.status is CampaignStatus.ENDED
    assert [e.event_type for e in fake_outbox.events] == [
        "BannerCampaignScheduled",
        "BannerCampaignEnded",
    ]


@pytest.mark.asyncio
async def test_schedule_campaign_raises_when_entitlement_targets_a_different_slot(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_slots: FakePlacementSlotReaderPort,
    fake_creatives: FakeCreativeReaderPort,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    """The use-case-level half of I-21's slot clause: even an ACTIVE entitlement must be booked
    against THIS campaign's own configured slot, not merely any slot."""
    slot = fake_slots.seed("HOMEPAGE_TOP")
    use_cases = _use_cases(
        fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
    )
    entitlement_id = await _create_active_entitlement(
        fake_entitlement_projection,
        target_id=uuid4(),  # a different slot's head_id
    )
    campaign = await use_cases.create_campaign(
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        entitlement_id=entitlement_id,
        schedule_start=_NOW + timedelta(days=1),
        schedule_end=_NOW + timedelta(days=8),
        priority=0,
        targeting=Targeting(),
        operator_account_id=uuid4(),
        now=_NOW,
    )
    with pytest.raises(CampaignNotEligibleError):
        await use_cases.schedule_campaign(campaign.id, operator_account_id=uuid4(), now=_NOW)
    assert len(fake_outbox.events) == 0
    assert slot.head_id != entitlement_id  # sanity: distinct ids, not a false-positive match


class TestUpdateCampaign:
    async def _draft_campaign(
        self,
        use_cases: CampaignUseCases,
        fake_slots: FakePlacementSlotReaderPort,
    ) -> UUID:
        slot = fake_slots.seed("HOMEPAGE_TOP")
        campaign = await use_cases.create_campaign(
            slot_key="HOMEPAGE_TOP",
            creative_media_asset_id=uuid4(),
            entitlement_id=uuid4(),
            schedule_start=_NOW + timedelta(days=1),
            schedule_end=_NOW + timedelta(days=8),
            priority=0,
            targeting=Targeting(),
            operator_account_id=uuid4(),
            now=_NOW,
        )
        assert campaign.placement_slot_id == slot.head_id
        return campaign.id

    @pytest.mark.asyncio
    async def test_update_campaign_replaces_schedule_and_targeting(
        self,
        fake_campaigns: FakeBannerCampaignRepository,
        fake_slots: FakePlacementSlotReaderPort,
        fake_creatives: FakeCreativeReaderPort,
        fake_entitlement_projection: FakeEntitlementProjectionRepository,
        fake_outbox: FakeOutbox,
    ) -> None:
        use_cases = _use_cases(
            fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
        )
        campaign_id = await self._draft_campaign(use_cases, fake_slots)

        updated = await use_cases.update_campaign(
            campaign_id,
            creative_media_asset_id=None,
            schedule_start=None,
            schedule_end=_NOW + timedelta(days=10),
            priority=5,
            targeting=Targeting(geo="UZ-TAS"),
            now=_NOW,
        )
        assert updated.schedule.end == _NOW + timedelta(days=10)
        assert updated.schedule.priority == 5
        assert updated.targeting.geo == "UZ-TAS"
        # no event -- DRAFT-only mutation, not a lifecycle transition (ADR-0004).
        assert len(fake_outbox.events) == 0

    @pytest.mark.asyncio
    async def test_update_campaign_refreshes_creative_status_when_creative_changes(
        self,
        fake_campaigns: FakeBannerCampaignRepository,
        fake_slots: FakePlacementSlotReaderPort,
        fake_creatives: FakeCreativeReaderPort,
        fake_entitlement_projection: FakeEntitlementProjectionRepository,
        fake_outbox: FakeOutbox,
    ) -> None:
        use_cases = _use_cases(
            fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
        )
        campaign_id = await self._draft_campaign(use_cases, fake_slots)
        new_creative_id = uuid4()
        fake_creatives.statuses[new_creative_id] = CreativeStatus.QUARANTINED

        updated = await use_cases.update_campaign(
            campaign_id,
            creative_media_asset_id=new_creative_id,
            schedule_start=None,
            schedule_end=None,
            priority=None,
            targeting=None,
            now=_NOW,
        )
        assert updated.creative_media_asset_id == new_creative_id
        assert updated.creative_status is CreativeStatus.QUARANTINED

    @pytest.mark.asyncio
    async def test_update_campaign_leaves_untouched_fields_alone_when_no_overrides_given(
        self,
        fake_campaigns: FakeBannerCampaignRepository,
        fake_slots: FakePlacementSlotReaderPort,
        fake_creatives: FakeCreativeReaderPort,
        fake_entitlement_projection: FakeEntitlementProjectionRepository,
        fake_outbox: FakeOutbox,
    ) -> None:
        use_cases = _use_cases(
            fake_campaigns, fake_slots, fake_creatives, fake_entitlement_projection, fake_outbox
        )
        campaign_id = await self._draft_campaign(use_cases, fake_slots)
        before = await use_cases.get_campaign(campaign_id)

        updated = await use_cases.update_campaign(
            campaign_id,
            creative_media_asset_id=None,
            schedule_start=None,
            schedule_end=None,
            priority=None,
            targeting=None,
            now=_NOW,
        )
        assert updated.schedule == before.schedule
        assert updated.targeting == before.targeting
        assert updated.creative_media_asset_id == before.creative_media_asset_id
