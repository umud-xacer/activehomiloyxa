"""Unit tests for `BannerServingUseCases` (FR-BANNER-004/005; ADR-0004's `/banners/*` operations).
Includes a structural test proving `serve_banner` never depends on a cross-module port at all
(SAD Sec 19: "fast, never blocks on another bounded context")."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from ads.application.exceptions import CampaignNotFoundError
from ads.application.ports import EntitlementSnapshot
from ads.application.serve_use_cases import BannerServingUseCases
from ads.domain import BannerCampaign, CreativeStatus, Schedule, Targeting

from .conftest import (
    FakeBannerCampaignRepository,
    FakeEntitlementProjectionRepository,
    FakeOutbox,
)

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def test_serve_banner_never_depends_on_a_cross_module_port() -> None:
    """`BannerServingUseCases.__init__` accepts only `campaigns`/`entitlements`/`outbox` -- no
    `PlacementSlotReaderPort`/`CreativeReaderPort` parameter exists at all, so the hot serve path
    cannot accidentally grow a live configuration/media call."""
    params = set(inspect.signature(BannerServingUseCases.__init__).parameters)
    assert params == {"self", "campaigns", "entitlements", "outbox"}


async def _running_campaign(
    campaigns: FakeBannerCampaignRepository,
    entitlements: FakeEntitlementProjectionRepository,
    *,
    slot_key: str = "HOMEPAGE_TOP",
    priority: int = 0,
    creative_status: CreativeStatus = CreativeStatus.CLEAN,
    entitlement_active: bool = True,
    targeting: Targeting = Targeting(),
) -> BannerCampaign:
    entitlement_id = uuid4()
    placement_slot_id = uuid4()
    await entitlements.upsert(
        EntitlementSnapshot(
            entitlement_id=entitlement_id,
            target_id=placement_slot_id,
            valid_from=_NOW - timedelta(days=1),
            valid_until=(_NOW + timedelta(days=30))
            if entitlement_active
            else (_NOW - timedelta(days=1)),
            activation_state="ACTIVE" if entitlement_active else "EXPIRED",
        )
    )
    campaign = (
        BannerCampaign.create(
            campaign_id=uuid4(),
            placement_slot_id=placement_slot_id,
            placement_slot_version_id=uuid4(),
            slot_key=slot_key,
            creative_media_asset_id=uuid4(),
            creative_status=creative_status,
            entitlement_id=entitlement_id,
            schedule=Schedule(
                start=_NOW - timedelta(days=1), end=_NOW + timedelta(days=1), priority=priority
            ),
            targeting=targeting,
            now=_NOW,
        )
        .schedule_campaign(now=_NOW)
        .start(now=_NOW)
    )
    await campaigns.add(campaign)
    return campaign


@pytest.mark.asyncio
async def test_serve_banner_returns_the_single_eligible_campaign(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    campaign = await _running_campaign(fake_campaigns, fake_entitlement_projection)
    use_cases = BannerServingUseCases(
        campaigns=fake_campaigns, entitlements=fake_entitlement_projection, outbox=fake_outbox
    )
    served = await use_cases.serve_banner(
        slot_key="HOMEPAGE_TOP", category_id=None, geo=None, language=None, now=_NOW
    )
    assert served is not None
    assert served.id == campaign.id


@pytest.mark.asyncio
async def test_serve_banner_selects_the_highest_priority_candidate(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    await _running_campaign(fake_campaigns, fake_entitlement_projection, priority=1)
    higher = await _running_campaign(fake_campaigns, fake_entitlement_projection, priority=5)
    use_cases = BannerServingUseCases(
        campaigns=fake_campaigns, entitlements=fake_entitlement_projection, outbox=fake_outbox
    )
    served = await use_cases.serve_banner(
        slot_key="HOMEPAGE_TOP", category_id=None, geo=None, language=None, now=_NOW
    )
    assert served is not None
    assert served.id == higher.id


@pytest.mark.asyncio
async def test_serve_banner_returns_none_when_entitlement_is_inactive(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    await _running_campaign(fake_campaigns, fake_entitlement_projection, entitlement_active=False)
    use_cases = BannerServingUseCases(
        campaigns=fake_campaigns, entitlements=fake_entitlement_projection, outbox=fake_outbox
    )
    served = await use_cases.serve_banner(
        slot_key="HOMEPAGE_TOP", category_id=None, geo=None, language=None, now=_NOW
    )
    assert served is None


@pytest.mark.asyncio
async def test_serve_banner_returns_none_when_creative_is_quarantined(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    await _running_campaign(
        fake_campaigns, fake_entitlement_projection, creative_status=CreativeStatus.QUARANTINED
    )
    use_cases = BannerServingUseCases(
        campaigns=fake_campaigns, entitlements=fake_entitlement_projection, outbox=fake_outbox
    )
    served = await use_cases.serve_banner(
        slot_key="HOMEPAGE_TOP", category_id=None, geo=None, language=None, now=_NOW
    )
    assert served is None


@pytest.mark.asyncio
async def test_serve_banner_returns_none_for_a_different_slot(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    await _running_campaign(fake_campaigns, fake_entitlement_projection, slot_key="HOMEPAGE_TOP")
    use_cases = BannerServingUseCases(
        campaigns=fake_campaigns, entitlements=fake_entitlement_projection, outbox=fake_outbox
    )
    served = await use_cases.serve_banner(
        slot_key="CATEGORY_SIDEBAR", category_id=None, geo=None, language=None, now=_NOW
    )
    assert served is None


@pytest.mark.asyncio
async def test_record_impression_appends_a_metric_event_and_no_counter_mutation(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    campaign = await _running_campaign(fake_campaigns, fake_entitlement_projection)
    use_cases = BannerServingUseCases(
        campaigns=fake_campaigns, entitlements=fake_entitlement_projection, outbox=fake_outbox
    )
    await use_cases.record_impression(campaign.id, now=_NOW)
    assert len(fake_outbox.events) == 1
    assert fake_outbox.events[0].event_type == "BannerImpressionRecorded"
    unchanged = await fake_campaigns.get_by_id(campaign.id)
    assert unchanged == campaign  # no state mutation at all (I-23)


@pytest.mark.asyncio
async def test_record_click_appends_a_metric_event(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    campaign = await _running_campaign(fake_campaigns, fake_entitlement_projection)
    use_cases = BannerServingUseCases(
        campaigns=fake_campaigns, entitlements=fake_entitlement_projection, outbox=fake_outbox
    )
    await use_cases.record_click(campaign.id, now=_NOW)
    assert len(fake_outbox.events) == 1
    assert fake_outbox.events[0].event_type == "BannerClickRecorded"


@pytest.mark.asyncio
async def test_record_impression_raises_not_found_for_unknown_campaign(
    fake_campaigns: FakeBannerCampaignRepository,
    fake_entitlement_projection: FakeEntitlementProjectionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = BannerServingUseCases(
        campaigns=fake_campaigns, entitlements=fake_entitlement_projection, outbox=fake_outbox
    )
    with pytest.raises(CampaignNotFoundError):
        await use_cases.record_impression(uuid4(), now=_NOW)
