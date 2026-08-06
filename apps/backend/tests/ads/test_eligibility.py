"""Unit tests for `CampaignEligibilityPolicy` (DDD Sec 9 I-21, I-20).

I-21 (quoted verbatim): "A BannerCampaign serves only within its schedule, matching targeting, in
its configured slot, while its booking entitlement is active." Exactly four clauses, tested
individually below (`test_I21_...`). I-20's creative-cleanliness clause is deliberately a
SEPARATE, distinctly-named test (`test_I20_...`) -- I-21's own text says nothing about creative
status; conflating the two would overstate what I-21 itself requires (see `ads/README.md`
"Design notes").
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from ads.domain import (
    BannerCampaign,
    CampaignEligibilityPolicy,
    CreativeStatus,
    Schedule,
    Targeting,
)

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _make_campaign(
    *,
    slot_key: str = "HOMEPAGE_TOP",
    start: datetime = _NOW - timedelta(days=1),
    end: datetime = _NOW + timedelta(days=1),
    targeting: Targeting = Targeting(),
    creative_status: CreativeStatus = CreativeStatus.CLEAN,
) -> BannerCampaign:
    return BannerCampaign.create(
        campaign_id=uuid4(),
        placement_slot_id=uuid4(),
        placement_slot_version_id=uuid4(),
        slot_key=slot_key,
        creative_media_asset_id=uuid4(),
        creative_status=creative_status,
        entitlement_id=uuid4(),
        schedule=Schedule(start=start, end=end, priority=0),
        targeting=targeting,
        now=_NOW,
    )


def _base_kwargs() -> dict[str, Any]:
    return {
        "requested_slot_key": "HOMEPAGE_TOP",
        "requested_category_id": None,
        "requested_geo": None,
        "requested_language": None,
        "entitlement_active": True,
        "now": _NOW,
    }


def test_I21_all_four_clauses_satisfied_is_eligible() -> None:
    campaign = _make_campaign()
    assert CampaignEligibilityPolicy.is_eligible_under_i21(campaign, **_base_kwargs()) is True


def test_I21_outside_schedule_window_is_not_eligible() -> None:
    campaign = _make_campaign(start=_NOW + timedelta(days=1), end=_NOW + timedelta(days=2))
    assert CampaignEligibilityPolicy.is_eligible_under_i21(campaign, **_base_kwargs()) is False


def test_I21_targeting_mismatch_is_not_eligible() -> None:
    campaign = _make_campaign(targeting=Targeting(geo="UZ-TAS"))
    kwargs = _base_kwargs()
    kwargs["requested_geo"] = "UZ-SAM"
    assert CampaignEligibilityPolicy.is_eligible_under_i21(campaign, **kwargs) is False


def test_I21_wrong_slot_is_not_eligible() -> None:
    campaign = _make_campaign(slot_key="HOMEPAGE_TOP")
    kwargs = _base_kwargs()
    kwargs["requested_slot_key"] = "CATEGORY_SIDEBAR"
    assert CampaignEligibilityPolicy.is_eligible_under_i21(campaign, **kwargs) is False


def test_I21_inactive_entitlement_is_not_eligible() -> None:
    campaign = _make_campaign()
    kwargs = _base_kwargs()
    kwargs["entitlement_active"] = False
    assert CampaignEligibilityPolicy.is_eligible_under_i21(campaign, **kwargs) is False


def test_I20_clean_creative_is_eligible() -> None:
    campaign = _make_campaign(creative_status=CreativeStatus.CLEAN)
    assert CampaignEligibilityPolicy.is_eligible_under_i20(campaign) is True


def test_I20_quarantined_creative_is_not_eligible() -> None:
    campaign = _make_campaign(creative_status=CreativeStatus.QUARANTINED)
    assert CampaignEligibilityPolicy.is_eligible_under_i20(campaign) is False


def test_I20_pending_creative_is_not_eligible() -> None:
    """Not yet CLEAN -- a scan still in progress must not serve either (I-20's "never delivered"
    is a positive-clean requirement, not merely "not known-bad")."""
    campaign = _make_campaign(creative_status=CreativeStatus.PENDING)
    assert CampaignEligibilityPolicy.is_eligible_under_i20(campaign) is False


def test_is_servable_requires_both_i21_and_i20() -> None:
    clean_campaign = _make_campaign(creative_status=CreativeStatus.CLEAN)
    quarantined_campaign = _make_campaign(creative_status=CreativeStatus.QUARANTINED)
    kwargs = _base_kwargs()
    assert CampaignEligibilityPolicy.is_servable(clean_campaign, **kwargs) is True
    assert CampaignEligibilityPolicy.is_servable(quarantined_campaign, **kwargs) is False


def test_is_servable_fails_when_i21_holds_but_i20_does_not_even_with_active_entitlement() -> None:
    """A campaign that passes every I-21 clause but has a quarantined creative must still never
    serve -- proves the two gates are independently enforced, not just the weaker of the two."""
    campaign = _make_campaign(creative_status=CreativeStatus.QUARANTINED)
    kwargs = _base_kwargs()
    assert CampaignEligibilityPolicy.is_eligible_under_i21(campaign, **kwargs) is True
    assert CampaignEligibilityPolicy.is_servable(campaign, **kwargs) is False
