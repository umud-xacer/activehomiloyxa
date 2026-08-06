"""Unit tests for the `BannerCampaign` aggregate's own state machine (DDD Sec 5.9). Mirrors
`billing.domain.order.Order`'s test style (`test_order.py`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from ads.domain import (
    BannerCampaign,
    CampaignStatus,
    CreativeStatus,
    IllegalCampaignStateTransitionError,
    Schedule,
    Targeting,
)

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _make_campaign(
    *, status: CampaignStatus = CampaignStatus.DRAFT, **schedule_kwargs: object
) -> BannerCampaign:
    schedule = Schedule(
        start=schedule_kwargs.get("start", _NOW + timedelta(days=1)),  # type: ignore[arg-type]
        end=schedule_kwargs.get("end", _NOW + timedelta(days=8)),  # type: ignore[arg-type]
        priority=0,
    )
    campaign = BannerCampaign.create(
        campaign_id=uuid4(),
        placement_slot_id=uuid4(),
        placement_slot_version_id=uuid4(),
        slot_key="HOMEPAGE_TOP",
        creative_media_asset_id=uuid4(),
        creative_status=CreativeStatus.CLEAN,
        entitlement_id=uuid4(),
        schedule=schedule,
        targeting=Targeting(),
        now=_NOW,
    )
    if status is not CampaignStatus.DRAFT:
        object.__setattr__(campaign, "status", status)
    return campaign


def test_create_starts_in_draft() -> None:
    campaign = _make_campaign()
    assert campaign.status is CampaignStatus.DRAFT


def test_update_succeeds_while_draft() -> None:
    campaign = _make_campaign()
    new_schedule = Schedule(
        start=_NOW + timedelta(days=2), end=_NOW + timedelta(days=9), priority=5
    )
    updated = campaign.update(schedule=new_schedule, now=_NOW)
    assert updated.schedule.priority == 5


def test_update_fails_once_scheduled() -> None:
    campaign = _make_campaign(status=CampaignStatus.SCHEDULED)
    with pytest.raises(IllegalCampaignStateTransitionError):
        campaign.update(schedule=campaign.schedule, now=_NOW)


def test_schedule_campaign_from_draft_is_legal() -> None:
    campaign = _make_campaign()
    scheduled = campaign.schedule_campaign(now=_NOW)
    assert scheduled.status is CampaignStatus.SCHEDULED


def test_schedule_campaign_from_a_non_draft_status_is_illegal() -> None:
    campaign = _make_campaign(status=CampaignStatus.SCHEDULED)
    with pytest.raises(IllegalCampaignStateTransitionError):
        campaign.schedule_campaign(now=_NOW)


def test_start_from_scheduled_is_legal() -> None:
    campaign = _make_campaign(status=CampaignStatus.SCHEDULED)
    started = campaign.start(now=_NOW)
    assert started.status is CampaignStatus.RUNNING


@pytest.mark.parametrize(
    "status",
    [CampaignStatus.DRAFT, CampaignStatus.RUNNING, CampaignStatus.PAUSED, CampaignStatus.ENDED],
)
def test_start_from_a_non_scheduled_status_is_illegal(status: CampaignStatus) -> None:
    campaign = _make_campaign(status=status)
    with pytest.raises(IllegalCampaignStateTransitionError):
        campaign.start(now=_NOW)


@pytest.mark.parametrize("status", [CampaignStatus.SCHEDULED, CampaignStatus.RUNNING])
def test_pause_from_scheduled_or_running_is_legal(status: CampaignStatus) -> None:
    campaign = _make_campaign(status=status)
    paused = campaign.pause(now=_NOW)
    assert paused.status is CampaignStatus.PAUSED


@pytest.mark.parametrize(
    "status", [CampaignStatus.DRAFT, CampaignStatus.PAUSED, CampaignStatus.ENDED]
)
def test_pause_from_any_other_status_is_illegal(status: CampaignStatus) -> None:
    campaign = _make_campaign(status=status)
    with pytest.raises(IllegalCampaignStateTransitionError):
        campaign.pause(now=_NOW)


def test_resume_before_schedule_start_returns_to_scheduled() -> None:
    campaign = _make_campaign(status=CampaignStatus.PAUSED)
    resumed = campaign.resume(now=_NOW)  # schedule starts tomorrow
    assert resumed.status is CampaignStatus.SCHEDULED


def test_resume_within_schedule_window_returns_to_running() -> None:
    campaign = _make_campaign(
        status=CampaignStatus.PAUSED,
        start=_NOW - timedelta(days=1),
        end=_NOW + timedelta(days=1),
    )
    resumed = campaign.resume(now=_NOW)
    assert resumed.status is CampaignStatus.RUNNING


def test_resume_from_a_non_paused_status_is_illegal() -> None:
    campaign = _make_campaign(status=CampaignStatus.RUNNING)
    with pytest.raises(IllegalCampaignStateTransitionError):
        campaign.resume(now=_NOW)


@pytest.mark.parametrize(
    "status", [CampaignStatus.SCHEDULED, CampaignStatus.RUNNING, CampaignStatus.PAUSED]
)
def test_end_from_any_live_status_is_legal(status: CampaignStatus) -> None:
    campaign = _make_campaign(status=status)
    ended = campaign.end(now=_NOW)
    assert ended.status is CampaignStatus.ENDED


def test_end_from_draft_is_illegal() -> None:
    campaign = _make_campaign(status=CampaignStatus.DRAFT)
    with pytest.raises(IllegalCampaignStateTransitionError):
        campaign.end(now=_NOW)


def test_end_from_already_ended_is_illegal() -> None:
    campaign = _make_campaign(status=CampaignStatus.ENDED)
    with pytest.raises(IllegalCampaignStateTransitionError):
        campaign.end(now=_NOW)


def test_mark_creative_status_is_callable_in_any_status() -> None:
    """A late quarantine on an already-RUNNING campaign must still be reflected (I-20)."""
    campaign = _make_campaign(status=CampaignStatus.RUNNING)
    updated = campaign.mark_creative_status(CreativeStatus.QUARANTINED, now=_NOW)
    assert updated.creative_status is CreativeStatus.QUARANTINED
    assert updated.status is CampaignStatus.RUNNING  # unaffected


def test_no_impression_or_click_counter_fields_exist_on_the_aggregate() -> None:
    """I-23/Database Architecture's counters-correction note: engagement is a metric event only."""
    campaign = _make_campaign()
    field_names = set(campaign.__dataclass_fields__)
    assert not any("impression" in f.lower() or "click" in f.lower() for f in field_names)
