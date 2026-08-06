"""ads/application -- `CampaignUseCases` (Task P-14). Operator-facing campaign CRUD/lifecycle
(FR-BANNER-002/003; ADR-0004's `/admin/campaigns*` operations). Mirrors `billing.application.
order_use_cases.OrderUseCases`'s style: use cases receive their ports via the constructor
(Playbook Sec 6), never construct a concrete adapter.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from ads.application.exceptions import (
    CampaignNotFoundError,
    EntitlementNotFoundError,
    SlotNotFoundError,
)
from ads.application.ports import (
    BannerCampaignRepository,
    CreativeReaderPort,
    EntitlementProjectionRepository,
    PlacementSlotReaderPort,
)
from ads.domain import (
    BannerCampaign,
    CampaignEligibilityPolicy,
    CampaignNotEligibleError,
    CampaignStatus,
    Schedule,
    Targeting,
)
from contracts.events.ads import BannerCampaignEnded, BannerCampaignScheduled, BannerCampaignStarted
from shared_kernel import OutboxPort


class CampaignUseCases:
    def __init__(
        self,
        *,
        campaigns: BannerCampaignRepository,
        slots: PlacementSlotReaderPort,
        creatives: CreativeReaderPort,
        entitlements: EntitlementProjectionRepository,
        outbox: OutboxPort,
    ) -> None:
        self._campaigns = campaigns
        self._slots = slots
        self._creatives = creatives
        self._entitlements = entitlements
        self._outbox = outbox

    async def create_campaign(
        self,
        *,
        slot_key: str,
        creative_media_asset_id: UUID,
        entitlement_id: UUID,
        schedule_start: datetime,
        schedule_end: datetime,
        priority: int,
        targeting: Targeting,
        operator_account_id: UUID,
        now: datetime,
    ) -> BannerCampaign:
        """FR-BANNER-002/003. Resolves the slot (FR-BANNER-001's own configuration-authored
        inventory) and the creative's current scan status synchronously -- both are low-frequency
        admin actions, not the hot `serveBanner` path, so a cross-module read here is acceptable
        (X-06's own "synchronous interface" half, not the "never blocks" constraint that applies
        only to serving)."""
        slot = await self._slots.get_slot_by_key(slot_key)
        if slot is None:
            raise SlotNotFoundError(slot_key)
        creative_status = await self._creatives.get_creative_status(creative_media_asset_id)
        campaign = BannerCampaign.create(
            campaign_id=uuid4(),
            placement_slot_id=slot.head_id,
            placement_slot_version_id=slot.version_id,
            slot_key=slot.slot_key,
            creative_media_asset_id=creative_media_asset_id,
            creative_status=creative_status,
            entitlement_id=entitlement_id,
            schedule=Schedule(start=schedule_start, end=schedule_end, priority=priority),
            targeting=targeting,
            now=now,
        )
        await self._campaigns.add(campaign)
        return campaign

    async def get_campaign(self, campaign_id: UUID) -> BannerCampaign:
        campaign = await self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise CampaignNotFoundError(campaign_id)
        return campaign

    async def list_campaigns(
        self,
        *,
        status: CampaignStatus | None,
        slot_key: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[BannerCampaign], str | None]:
        return await self._campaigns.list_for_operator(
            status=status, slot_key=slot_key, cursor=cursor, limit=limit
        )

    async def update_campaign(
        self,
        campaign_id: UUID,
        *,
        creative_media_asset_id: UUID | None,
        schedule_start: datetime | None,
        schedule_end: datetime | None,
        priority: int | None,
        targeting: Targeting | None,
        now: datetime,
    ) -> BannerCampaign:
        """DRAFT only (`BannerCampaign.update`'s own guard raises `IllegalCampaignStateTransitionError`
        otherwise)."""
        campaign = await self.get_campaign(campaign_id)
        creative_status = campaign.creative_status
        if creative_media_asset_id is not None:
            creative_status = await self._creatives.get_creative_status(creative_media_asset_id)
        new_schedule = campaign.schedule
        if schedule_start is not None or schedule_end is not None or priority is not None:
            new_schedule = Schedule(
                start=schedule_start or campaign.schedule.start,
                end=schedule_end or campaign.schedule.end,
                priority=priority if priority is not None else campaign.schedule.priority,
            )
        updated = campaign.update(
            creative_media_asset_id=creative_media_asset_id,
            creative_status=creative_status,
            schedule=new_schedule,
            targeting=targeting,
            now=now,
        )
        return await self._campaigns.save(updated)

    async def schedule_campaign(
        self, campaign_id: UUID, *, operator_account_id: UUID, now: datetime
    ) -> BannerCampaign:
        """`DRAFT -> SCHEDULED`. Runs I-21's slot/targeting/entitlement-active checks (deferring
        the "currently within schedule" clause, since the window is typically future at this
        point) and I-20's creative-clean check BEFORE the state transition -- a campaign an
        operator cannot yet make live is refused here with `CampaignNotEligibleError`, never
        silently scheduled anyway."""
        campaign = await self.get_campaign(campaign_id)
        entitlement = await self._entitlements.get_by_id(campaign.entitlement_id)
        if entitlement is None:
            raise EntitlementNotFoundError(campaign.entitlement_id)
        if entitlement.target_id != campaign.placement_slot_id:
            raise CampaignNotEligibleError(
                "entitlement's booked slot does not match this campaign's configured slot"
            )
        if not entitlement.is_active(now=now):
            raise CampaignNotEligibleError("booking entitlement is not active")
        if not CampaignEligibilityPolicy.is_eligible_under_i20(campaign):
            raise CampaignNotEligibleError("creative is not CLEAN (I-20)")
        scheduled = campaign.schedule_campaign(now=now)
        saved = await self._campaigns.save(scheduled)
        await self._outbox.append(
            BannerCampaignScheduled(
                event_id=uuid4(),
                occurred_at=now,
                actor=operator_account_id,
                aggregate_type="BannerCampaign",
                aggregate_id=saved.id,
                payload={"campaignId": str(saved.id), "slotKey": saved.slot_key},
            )
        )
        return saved

    async def pause_campaign(self, campaign_id: UUID, *, now: datetime) -> BannerCampaign:
        campaign = await self.get_campaign(campaign_id)
        paused = campaign.pause(now=now)
        return await self._campaigns.save(paused)

    async def resume_campaign(self, campaign_id: UUID, *, now: datetime) -> BannerCampaign:
        campaign = await self.get_campaign(campaign_id)
        resumed = campaign.resume(now=now)
        return await self._campaigns.save(resumed)

    async def end_campaign(
        self, campaign_id: UUID, *, operator_account_id: UUID, now: datetime
    ) -> BannerCampaign:
        campaign = await self.get_campaign(campaign_id)
        ended = campaign.end(now=now)
        saved = await self._campaigns.save(ended)
        await self._outbox.append(
            BannerCampaignEnded(
                event_id=uuid4(),
                occurred_at=now,
                actor=operator_account_id,
                aggregate_type="BannerCampaign",
                aggregate_id=saved.id,
                payload={"campaignId": str(saved.id), "slotKey": saved.slot_key},
            )
        )
        return saved

    async def sweep_schedule_transitions(self, *, now: datetime) -> tuple[int, int]:
        """`CampaignScheduleSweepWorker`'s own use case: natural `SCHEDULED -> RUNNING`
        (`schedule.start` reached, emits `BannerCampaignStarted`) and natural `... -> ENDED`
        (`schedule.end` passed, emits `BannerCampaignEnded` -- the SAME event `end_campaign`'s
        own operator early-stop emits, since the frozen catalogue draws no distinction between
        the two triggers). Mirrors `billing.application.entitlement_use_cases.EntitlementUseCases.
        sweep_expired`'s one-aggregate-per-iteration transaction discipline (DEC-09)."""
        started = 0
        for campaign in await self._campaigns.list_due_to_start(now=now):
            saved = await self._campaigns.save(campaign.start(now=now))
            await self._outbox.append(
                BannerCampaignStarted(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=None,
                    aggregate_type="BannerCampaign",
                    aggregate_id=saved.id,
                    payload={"campaignId": str(saved.id), "slotKey": saved.slot_key},
                )
            )
            started += 1

        ended = 0
        for campaign in await self._campaigns.list_due_to_end(now=now):
            saved = await self._campaigns.save(campaign.end(now=now))
            await self._outbox.append(
                BannerCampaignEnded(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=None,
                    aggregate_type="BannerCampaign",
                    aggregate_id=saved.id,
                    payload={"campaignId": str(saved.id), "slotKey": saved.slot_key},
                )
            )
            ended += 1
        return started, ended
