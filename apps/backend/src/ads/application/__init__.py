"""ads/application -- use cases (Task P-14). Imports `ads.domain` and `shared_kernel` only;
never imported by another module (`application/` is never part of a module's public surface)."""

from __future__ import annotations

from ads.application.campaign_use_cases import CampaignUseCases
from ads.application.exceptions import (
    AdsApplicationError,
    CampaignNotFoundError,
    EntitlementNotFoundError,
    SlotNotFoundError,
)
from ads.application.ports import (
    BannerCampaignRepository,
    CreativeReaderPort,
    EntitlementProjectionRepository,
    EntitlementSnapshot,
    PlacementSlotReaderPort,
    SlotSnapshot,
)
from ads.application.serve_use_cases import BannerServingUseCases

__all__ = [
    "AdsApplicationError",
    "BannerCampaignRepository",
    "BannerServingUseCases",
    "CampaignNotFoundError",
    "CampaignUseCases",
    "CreativeReaderPort",
    "EntitlementNotFoundError",
    "EntitlementProjectionRepository",
    "EntitlementSnapshot",
    "PlacementSlotReaderPort",
    "SlotNotFoundError",
    "SlotSnapshot",
]
