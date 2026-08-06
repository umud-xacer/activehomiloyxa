"""ads/domain -- the `BannerCampaign` aggregate, value objects, `CampaignEligibilityPolicy`
(I-21/I-20), and typed domain exceptions (Task P-14). Imports `shared_kernel` only (Clean
Architecture rule 1); never imported by another module (`domain/` is never part of a module's
public surface, AIR-02)."""

from __future__ import annotations

from ads.domain.banner_campaign import BannerCampaign
from ads.domain.eligibility import CampaignEligibilityPolicy
from ads.domain.exceptions import (
    AdsDomainError,
    CampaignNotEligibleError,
    IllegalCampaignStateTransitionError,
    InvalidScheduleError,
)
from ads.domain.value_objects import CampaignStatus, CreativeStatus, Schedule, Targeting

__all__ = [
    "AdsDomainError",
    "BannerCampaign",
    "CampaignEligibilityPolicy",
    "CampaignNotEligibleError",
    "CampaignStatus",
    "CreativeStatus",
    "IllegalCampaignStateTransitionError",
    "InvalidScheduleError",
    "Schedule",
    "Targeting",
]
