"""ads -- ports (Task P-01 stubs, populated Task P-14 per ADR-0004). Abstract surface only
(typing.Protocol): no implementation, no aggregates, no ORM types. Each method's docstring cites
the OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.

Kept as the same two names SAD Sec 7.2's public-interface row already assigned ads
("Campaign commands", "serving queries") -- ADR-0004 gave those names real HTTP operations to
derive from; the class identities are unchanged from the P-01 stub.
"""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from ads.interfaces.dto import (
    BannerCampaign,
    BannerCampaignCreateRequest,
    BannerCampaignPage,
    BannerCampaignUpdateRequest,
    BannerServeView,
)


class CampaignCommandPort(Protocol):
    """Derived from OpenAPI operations: `createCampaign`, `endCampaign`, `getCampaign`,
    `listCampaigns`, `pauseCampaign`, `resumeCampaign`, `scheduleCampaign`, `updateCampaign`."""

    async def list_campaigns(
        self,
        status: Literal["DRAFT", "SCHEDULED", "RUNNING", "PAUSED", "ENDED"] | None = None,
        slot_key: str | None = None,
        cursor: str | None = None,
        limit: int | None = 20,
    ) -> BannerCampaignPage:
        """`GET /admin/campaigns` (operationId `listCampaigns`). List banner campaigns (operator)"""
        ...

    async def create_campaign(self, body: BannerCampaignCreateRequest) -> BannerCampaign:
        """`POST /admin/campaigns` (operationId `createCampaign`). Create a banner campaign (operator)"""
        ...

    async def get_campaign(self, campaign_id: UUID) -> BannerCampaign:
        """`GET /admin/campaigns/{campaignId}` (operationId `getCampaign`). Get a banner campaign (operator)"""
        ...

    async def update_campaign(
        self, campaign_id: UUID, body: BannerCampaignUpdateRequest
    ) -> BannerCampaign:
        """`PATCH /admin/campaigns/{campaignId}` (operationId `updateCampaign`). Update a banner campaign (operator)"""
        ...

    async def schedule_campaign(self, campaign_id: UUID) -> BannerCampaign:
        """`POST /admin/campaigns/{campaignId}/schedule` (operationId `scheduleCampaign`). Schedule a banner campaign (operator)"""
        ...

    async def pause_campaign(self, campaign_id: UUID) -> BannerCampaign:
        """`POST /admin/campaigns/{campaignId}/pause` (operationId `pauseCampaign`). Pause a banner campaign (operator)"""
        ...

    async def resume_campaign(self, campaign_id: UUID) -> BannerCampaign:
        """`POST /admin/campaigns/{campaignId}/resume` (operationId `resumeCampaign`). Resume a paused banner campaign (operator)"""
        ...

    async def end_campaign(self, campaign_id: UUID) -> BannerCampaign:
        """`POST /admin/campaigns/{campaignId}/end` (operationId `endCampaign`). End a banner campaign early (operator)"""
        ...


class BannerServingQueryPort(Protocol):
    """Derived from OpenAPI operations: `serveBanner`, `recordBannerImpression`,
    `recordBannerClick`."""

    async def serve_banner(
        self,
        slot_key: str,
        category_id: UUID | None = None,
        geo: str | None = None,
        language: Literal["uz_latn", "uz_cyrl", "ru", "en"] | None = None,
    ) -> BannerServeView | None:
        """`GET /banners/serve` (operationId `serveBanner`). Select and serve an eligible banner (public)"""
        ...

    async def record_banner_impression(self, campaign_id: UUID) -> None:
        """`POST /banners/{campaignId}/impressions` (operationId `recordBannerImpression`). Record a banner impression (public)"""
        ...

    async def record_banner_click(self, campaign_id: UUID) -> None:
        """`POST /banners/{campaignId}/clicks` (operationId `recordBannerClick`). Record a banner click (public)"""
        ...
