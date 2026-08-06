"""ads.interfaces -- the module's only importable public surface (AIR-02).

STATUS: real DTOs/ports/routers (Task P-14, ADR-0004) -- the P-01 marker stubs are now populated.
"""

from __future__ import annotations

from ads.interfaces.dto import (
    BannerCampaign,
    BannerCampaignCreateRequest,
    BannerCampaignPage,
    BannerCampaignUpdateRequest,
    BannerServeView,
    PageInfo,
    Targeting,
)
from ads.interfaces.ports import BannerServingQueryPort, CampaignCommandPort

__all__ = [
    "BannerCampaign",
    "BannerCampaignCreateRequest",
    "BannerCampaignPage",
    "BannerCampaignUpdateRequest",
    "BannerServeView",
    "BannerServingQueryPort",
    "CampaignCommandPort",
    "PageInfo",
    "Targeting",
]
