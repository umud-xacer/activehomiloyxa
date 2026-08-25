"""FastAPI routers implementing the `Ads`-tagged OpenAPI operations (`contracts/openapi.yaml`,
ADR-0004's original nine, plus `serveBannersMany` added for the carousel/native `AdSlot`
variants). Thin translation only: path/body -> use case call -> domain object -> already-frozen
`interfaces/dto.py` DTO. All business logic lives in `application`/`domain`; this module owns
none.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from ads.application import BannerServingUseCases, CampaignUseCases
from ads.domain import BannerCampaign as BannerCampaignDomain
from ads.domain import CampaignStatus
from ads.domain import Targeting as TargetingDomain
from ads.interfaces.auth import ActingOperator
from ads.interfaces.di import get_acting_operator, get_campaign_use_cases, get_serving_use_cases
from ads.interfaces.dto import (
    BannerCampaign,
    BannerCampaignCreateRequest,
    BannerCampaignPage,
    BannerCampaignUpdateRequest,
    BannerServeManyResult,
    BannerServeView,
    PageInfo,
    Targeting,
)

ads_admin_router = APIRouter(tags=["Ads"])
ads_public_router = APIRouter(tags=["Ads"])


def _clamp_limit(limit: int | None) -> int:
    return min(max(limit or 20, 1), 100)


def _to_targeting_domain(targeting: Targeting) -> TargetingDomain:
    return TargetingDomain(
        category_ids=tuple(targeting.category_ids),
        geo=targeting.geo,
        languages=tuple(targeting.languages),
    )


def _to_campaign_dto(campaign: BannerCampaignDomain) -> BannerCampaign:
    return BannerCampaign(
        id=campaign.id,
        slot_key=campaign.slot_key,
        creative_media_asset_id=campaign.creative_media_asset_id,
        entitlement_id=campaign.entitlement_id,
        schedule_start=campaign.schedule.start,
        schedule_end=campaign.schedule.end,
        priority=campaign.schedule.priority,
        targeting=Targeting(
            category_ids=list(campaign.targeting.category_ids),
            geo=campaign.targeting.geo,
            languages=cast(
                "list[Literal['uz_latn', 'uz_cyrl', 'ru', 'en']]",
                list(campaign.targeting.languages),
            ),
        ),
        status=campaign.status.value,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        target_url=campaign.target_url,
    )


# --- /admin/campaigns* (operator campaign management) -------------------------------------------


@ads_admin_router.get("/admin/campaigns", operation_id="listCampaigns")
async def list_campaigns(
    status: Literal["DRAFT", "SCHEDULED", "RUNNING", "PAUSED", "ENDED"] | None = None,
    slotKey: str | None = None,
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    _operator: ActingOperator = Depends(get_acting_operator),
    use_cases: CampaignUseCases = Depends(get_campaign_use_cases),
) -> BannerCampaignPage:
    page_limit = _clamp_limit(limit)
    campaigns, next_cursor = await use_cases.list_campaigns(
        status=CampaignStatus(status) if status else None,
        slot_key=slotKey,
        cursor=cursor,
        limit=page_limit,
    )
    return BannerCampaignPage(
        items=[_to_campaign_dto(c) for c in campaigns],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


@ads_admin_router.post("/admin/campaigns", operation_id="createCampaign", status_code=201)
async def create_campaign(
    body: BannerCampaignCreateRequest,
    operator: ActingOperator = Depends(get_acting_operator),
    use_cases: CampaignUseCases = Depends(get_campaign_use_cases),
) -> BannerCampaign:
    campaign = await use_cases.create_campaign(
        slot_key=body.slot_key,
        creative_media_asset_id=body.creative_media_asset_id,
        entitlement_id=body.entitlement_id,
        schedule_start=body.schedule_start,
        schedule_end=body.schedule_end,
        priority=body.priority,
        targeting=_to_targeting_domain(body.targeting),
        operator_account_id=operator.account_id.value,
        now=datetime.now(UTC),
        target_url=body.target_url,
    )
    return _to_campaign_dto(campaign)


@ads_admin_router.get("/admin/campaigns/{campaignId}", operation_id="getCampaign")
async def get_campaign(
    campaignId: UUID,
    _operator: ActingOperator = Depends(get_acting_operator),
    use_cases: CampaignUseCases = Depends(get_campaign_use_cases),
) -> BannerCampaign:
    campaign = await use_cases.get_campaign(campaignId)
    return _to_campaign_dto(campaign)


@ads_admin_router.patch("/admin/campaigns/{campaignId}", operation_id="updateCampaign")
async def update_campaign(
    campaignId: UUID,
    body: BannerCampaignUpdateRequest,
    _operator: ActingOperator = Depends(get_acting_operator),
    use_cases: CampaignUseCases = Depends(get_campaign_use_cases),
) -> BannerCampaign:
    campaign = await use_cases.update_campaign(
        campaignId,
        creative_media_asset_id=body.creative_media_asset_id,
        schedule_start=body.schedule_start,
        schedule_end=body.schedule_end,
        priority=body.priority,
        targeting=_to_targeting_domain(body.targeting) if body.targeting is not None else None,
        now=datetime.now(UTC),
        target_url=body.target_url,
    )
    return _to_campaign_dto(campaign)


@ads_admin_router.post("/admin/campaigns/{campaignId}/schedule", operation_id="scheduleCampaign")
async def schedule_campaign(
    campaignId: UUID,
    operator: ActingOperator = Depends(get_acting_operator),
    use_cases: CampaignUseCases = Depends(get_campaign_use_cases),
) -> BannerCampaign:
    campaign = await use_cases.schedule_campaign(
        campaignId, operator_account_id=operator.account_id.value, now=datetime.now(UTC)
    )
    return _to_campaign_dto(campaign)


@ads_admin_router.post("/admin/campaigns/{campaignId}/pause", operation_id="pauseCampaign")
async def pause_campaign(
    campaignId: UUID,
    _operator: ActingOperator = Depends(get_acting_operator),
    use_cases: CampaignUseCases = Depends(get_campaign_use_cases),
) -> BannerCampaign:
    campaign = await use_cases.pause_campaign(campaignId, now=datetime.now(UTC))
    return _to_campaign_dto(campaign)


@ads_admin_router.post("/admin/campaigns/{campaignId}/resume", operation_id="resumeCampaign")
async def resume_campaign(
    campaignId: UUID,
    _operator: ActingOperator = Depends(get_acting_operator),
    use_cases: CampaignUseCases = Depends(get_campaign_use_cases),
) -> BannerCampaign:
    campaign = await use_cases.resume_campaign(campaignId, now=datetime.now(UTC))
    return _to_campaign_dto(campaign)


@ads_admin_router.post("/admin/campaigns/{campaignId}/end", operation_id="endCampaign")
async def end_campaign(
    campaignId: UUID,
    operator: ActingOperator = Depends(get_acting_operator),
    use_cases: CampaignUseCases = Depends(get_campaign_use_cases),
) -> BannerCampaign:
    campaign = await use_cases.end_campaign(
        campaignId, operator_account_id=operator.account_id.value, now=datetime.now(UTC)
    )
    return _to_campaign_dto(campaign)


# --- /banners/* (public serving/engagement capture) ---------------------------------------------


@ads_public_router.get("/banners/serve", operation_id="serveBanner")
async def serve_banner(
    response: Response,
    slotKey: str,
    categoryId: UUID | None = None,
    geo: str | None = None,
    language: Literal["uz_latn", "uz_cyrl", "ru", "en"] | None = None,
    use_cases: BannerServingUseCases = Depends(get_serving_use_cases),
) -> BannerServeView | None:
    campaign = await use_cases.serve_banner(
        slot_key=slotKey,
        category_id=categoryId,
        geo=geo,
        language=language,
        now=datetime.now(UTC),
    )
    if campaign is None:
        response.status_code = 204
        return None
    return BannerServeView(
        campaign_id=campaign.id,
        slot_key=campaign.slot_key,
        creative_media_asset_id=campaign.creative_media_asset_id,
        target_url=campaign.target_url,
    )


@ads_public_router.get("/banners/serve-many", operation_id="serveBannersMany")
async def serve_banners_many(
    slotKey: str,
    categoryId: UUID | None = None,
    geo: str | None = None,
    language: Literal["uz_latn", "uz_cyrl", "ru", "en"] | None = None,
    limit: int | None = Query(default=6),
    use_cases: BannerServingUseCases = Depends(get_serving_use_cases),
) -> BannerServeManyResult:
    campaigns = await use_cases.serve_banners(
        slot_key=slotKey,
        category_id=categoryId,
        geo=geo,
        language=language,
        limit=min(max(limit or 6, 1), 12),
        now=datetime.now(UTC),
    )
    return BannerServeManyResult(
        items=[
            BannerServeView(
                campaign_id=c.id,
                slot_key=c.slot_key,
                creative_media_asset_id=c.creative_media_asset_id,
                target_url=c.target_url,
            )
            for c in campaigns
        ]
    )


@ads_public_router.post(
    "/banners/{campaignId}/impressions", operation_id="recordBannerImpression", status_code=202
)
async def record_banner_impression(
    campaignId: UUID,
    use_cases: BannerServingUseCases = Depends(get_serving_use_cases),
) -> None:
    await use_cases.record_impression(campaignId, now=datetime.now(UTC))


@ads_public_router.post(
    "/banners/{campaignId}/clicks", operation_id="recordBannerClick", status_code=202
)
async def record_banner_click(
    campaignId: UUID,
    use_cases: BannerServingUseCases = Depends(get_serving_use_cases),
) -> None:
    await use_cases.record_click(campaignId, now=datetime.now(UTC))
