"""ads/infrastructure -- SQLAlchemy repositories, the configuration/media adapters, entitlement/
media event projections, and the campaign schedule sweep worker (Task P-14). Never imported by
`ads.interfaces`/`application`/`domain` -- only the composition root (outside every module's
package tree) wires these concrete classes behind the ports `application/` declares."""

from __future__ import annotations

from ads.infrastructure.configuration_adapter import ConfigurationPlacementSlotAdapter
from ads.infrastructure.media_adapter import MediaCreativeStatusAdapter
from ads.infrastructure.persistence import (
    AdsBase,
    BannerCampaignRow,
    EntitlementProjectionRow,
    OutboxEventRow,
    ProcessedEventRow,
    SqlalchemyBannerCampaignRepository,
    SqlalchemyEntitlementProjectionRepository,
)
from ads.infrastructure.worker import CampaignScheduleSweepWorker

__all__ = [
    "AdsBase",
    "BannerCampaignRow",
    "CampaignScheduleSweepWorker",
    "ConfigurationPlacementSlotAdapter",
    "EntitlementProjectionRow",
    "MediaCreativeStatusAdapter",
    "OutboxEventRow",
    "ProcessedEventRow",
    "SqlalchemyBannerCampaignRepository",
    "SqlalchemyEntitlementProjectionRepository",
]
