"""ads/application -- `BannerServingUseCases` (Task P-14). FR-BANNER-004/005; ADR-0004's
`/banners/*` operations. Deliberately the FASTEST path in this module: `serve_banner` never
performs a cross-module call -- entitlement activation is read from ads' own local
`EntitlementProjectionRepository` (event-projected, never a live billing call; `billing` is fully
forbidden by `cross-module-ads` anyway), and creative status is read from the campaign's own
cached `creative_status` column (event-projected from media, never a live media call either).
This is what "fast, never blocks on another bounded context" (SAD Sec 19) means structurally,
not just as an aspiration.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from ads.application.exceptions import CampaignNotFoundError
from ads.application.ports import BannerCampaignRepository, EntitlementProjectionRepository
from ads.domain import BannerCampaign, CampaignEligibilityPolicy
from contracts.events.ads import BannerClickRecorded, BannerImpressionRecorded
from shared_kernel import OutboxPort


class BannerServingUseCases:
    def __init__(
        self,
        *,
        campaigns: BannerCampaignRepository,
        entitlements: EntitlementProjectionRepository,
        outbox: OutboxPort,
    ) -> None:
        self._campaigns = campaigns
        self._entitlements = entitlements
        self._outbox = outbox

    async def serve_banner(
        self,
        *,
        slot_key: str,
        category_id: UUID | None,
        geo: str | None,
        language: str | None,
        now: datetime,
    ) -> BannerCampaign | None:
        """FR-BANNER-004. Candidates are pre-filtered to `SCHEDULED`/`RUNNING` in this slot,
        ordered by `priority` descending (`list_candidates_for_serve`'s own contract) -- returns
        the first candidate `CampaignEligibilityPolicy.is_servable` accepts, or `None` (204) if
        no candidate clears both I-21 and I-20."""
        candidates = await self._campaigns.list_candidates_for_serve(slot_key=slot_key)
        for campaign in candidates:
            entitlement = await self._entitlements.get_by_id(campaign.entitlement_id)
            entitlement_active = entitlement is not None and entitlement.is_active(now=now)
            if CampaignEligibilityPolicy.is_servable(
                campaign,
                requested_slot_key=slot_key,
                requested_category_id=category_id,
                requested_geo=geo,
                requested_language=language,
                entitlement_active=entitlement_active,
                now=now,
            ):
                return campaign
        return None

    async def record_impression(self, campaign_id: UUID, *, now: datetime) -> None:
        """FR-BANNER-005/I-23: a metric event only -- no counter mutation on `BannerCampaign`
        (Database Architecture's counters-correction note)."""
        campaign = await self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError(campaign_id)
        await self._outbox.append(
            BannerImpressionRecorded(
                event_id=uuid4(),
                occurred_at=now,
                actor=None,
                aggregate_type="BannerCampaign",
                aggregate_id=campaign.id,
                payload={"campaignId": str(campaign.id), "slotKey": campaign.slot_key},
            )
        )

    async def record_click(self, campaign_id: UUID, *, now: datetime) -> None:
        """FR-BANNER-005/I-23: same discipline as `record_impression` -- metric event only."""
        campaign = await self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError(campaign_id)
        await self._outbox.append(
            BannerClickRecorded(
                event_id=uuid4(),
                occurred_at=now,
                actor=None,
                aggregate_type="BannerCampaign",
                aggregate_id=campaign.id,
                payload={"campaignId": str(campaign.id), "slotKey": campaign.slot_key},
            )
        )
