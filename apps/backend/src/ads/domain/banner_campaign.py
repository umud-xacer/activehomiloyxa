"""ads -- the `BannerCampaign` aggregate (DDD Sec 5.9 `AR: BannerCampaign [P]`). Persistence-
ignorant, mirrors `billing.domain.order.Order`'s style exactly: frozen dataclass, every state
transition returns a new instance via `dataclasses.replace`, guarded by a typed exception raised
before the replace.

Carries NO impression/click counters (Database Architecture's counters-correction note; I-23:
"only the closed v1 metric vocabulary is captured ... each metric records exactly once per
triggering event") -- engagement is `BannerImpressionRecorded`/`BannerClickRecorded` metric
events only, appended by the application layer, never a mutation of this aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from ads.domain.exceptions import IllegalCampaignStateTransitionError
from ads.domain.value_objects import CampaignStatus, CreativeStatus, Schedule, Targeting

_SCHEDULABLE_STATES = frozenset({CampaignStatus.DRAFT})
_PAUSABLE_STATES = frozenset({CampaignStatus.SCHEDULED, CampaignStatus.RUNNING})
_ENDABLE_STATES = frozenset(
    {CampaignStatus.SCHEDULED, CampaignStatus.RUNNING, CampaignStatus.PAUSED}
)
_MUTABLE_STATES = frozenset({CampaignStatus.DRAFT})


@dataclass(frozen=True)
class BannerCampaign:
    """References its slot/creative/entitlement by identifier only (DDD Sec 5.9 VOs: `SlotRef`,
    `CreativeRef`, `EntitlementRef`) -- never a duplicated copy of configuration's/media's/
    billing's own state, only `creative_status` (I-20's projected snapshot, mirroring `catalog.
    domain.image_attachment.ImageAttachment.status`'s exact role) and the resolved slot
    head/version ids (mirroring `billing.domain.value_objects.ProductSnapshot`'s "frozen at
    reference time" precedent for a configuration-owned identity)."""

    id: UUID
    placement_slot_id: UUID
    placement_slot_version_id: UUID
    slot_key: str
    """The configuration `PlacementSlotDefinition`'s own `SlotKey` -- cached read-only convenience
    for `serveBanner`'s query parameter, resolved once at `create()` and never re-resolved
    (a slot's `SlotKey` is immutable once published, Configuration Framework Sec 3.4)."""
    creative_media_asset_id: UUID
    creative_status: CreativeStatus
    entitlement_id: UUID
    schedule: Schedule
    targeting: Targeting
    status: CampaignStatus
    created_at: datetime
    updated_at: datetime
    lock_version: int = 0

    @staticmethod
    def create(
        *,
        campaign_id: UUID,
        placement_slot_id: UUID,
        placement_slot_version_id: UUID,
        slot_key: str,
        creative_media_asset_id: UUID,
        creative_status: CreativeStatus,
        entitlement_id: UUID,
        schedule: Schedule,
        targeting: Targeting,
        now: datetime,
    ) -> BannerCampaign:
        """FR-BANNER-002/003: create in `DRAFT`. `creative_status` is passed in already-resolved
        (the application layer read it from `CreativeReaderPort` synchronously at this admin
        action) rather than defaulting to `PENDING` here -- unlike `ImageAttachment`, which
        starts `PENDING` because attaching truly never blocks on media's pipeline (QR-05), a
        campaign's own creative is created against an asset that (per FR-MEDIA) was already
        uploaded and, in the ordinary flow, already scanned by the time an operator references
        it in a campaign."""
        return BannerCampaign(
            id=campaign_id,
            placement_slot_id=placement_slot_id,
            placement_slot_version_id=placement_slot_version_id,
            slot_key=slot_key,
            creative_media_asset_id=creative_media_asset_id,
            creative_status=creative_status,
            entitlement_id=entitlement_id,
            schedule=schedule,
            targeting=targeting,
            status=CampaignStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        *,
        creative_media_asset_id: UUID | None = None,
        creative_status: CreativeStatus | None = None,
        schedule: Schedule | None = None,
        targeting: Targeting | None = None,
        now: datetime,
    ) -> BannerCampaign:
        """Mutates schedule/targeting/creative while still `DRAFT` only -- once scheduled, a
        campaign's own commitments are fixed (mirrors `Order.create`'s "no create-then-mutate
        past the point another party could already be relying on it" discipline)."""
        if self.status not in _MUTABLE_STATES:
            raise IllegalCampaignStateTransitionError("update", self.status.value)
        return replace(
            self,
            creative_media_asset_id=creative_media_asset_id or self.creative_media_asset_id,
            creative_status=creative_status or self.creative_status,
            schedule=schedule or self.schedule,
            targeting=targeting if targeting is not None else self.targeting,
            updated_at=now,
        )

    def schedule_campaign(self, *, now: datetime) -> BannerCampaign:
        """`DRAFT -> SCHEDULED`. The application layer runs I-21's slot/targeting/entitlement-
        active checks (deferring only the "currently within schedule" clause, since the window is
        typically future at scheduling time) via `CampaignEligibilityPolicy` BEFORE calling this
        -- this method only enforces the state-machine shape, matching `Order.mark_paid`'s own
        division of labour (guard here, business-rule check in the use case)."""
        if self.status not in _SCHEDULABLE_STATES:
            raise IllegalCampaignStateTransitionError("schedule", self.status.value)
        return replace(self, status=CampaignStatus.SCHEDULED, updated_at=now)

    def start(self, *, now: datetime) -> BannerCampaign:
        """`SCHEDULED -> RUNNING`. Called by `CampaignScheduleSweepWorker` when `schedule.start`
        is reached -- never a request-path use case (no OpenAPI operation "starts" a campaign
        directly; ADR-0004 only exposes schedule/pause/resume/end)."""
        if self.status is not CampaignStatus.SCHEDULED:
            raise IllegalCampaignStateTransitionError("start", self.status.value)
        return replace(self, status=CampaignStatus.RUNNING, updated_at=now)

    def pause(self, *, now: datetime) -> BannerCampaign:
        """`SCHEDULED | RUNNING -> PAUSED`. No domain event -- `contracts/events/ads.py` names
        only Scheduled/Started/Ended (ADR-0004)."""
        if self.status not in _PAUSABLE_STATES:
            raise IllegalCampaignStateTransitionError("pause", self.status.value)
        return replace(self, status=CampaignStatus.PAUSED, updated_at=now)

    def resume(self, *, now: datetime) -> BannerCampaign:
        """`PAUSED -> SCHEDULED | RUNNING`, decided by whether `now` already falls inside the
        schedule window -- resuming before `schedule.start` returns to `SCHEDULED` (the sweep
        worker will start it naturally later); resuming inside the window returns straight to
        `RUNNING`. No domain event, same reason as `pause`."""
        if self.status is not CampaignStatus.PAUSED:
            raise IllegalCampaignStateTransitionError("resume", self.status.value)
        next_status = (
            CampaignStatus.RUNNING if self.schedule.covers(now) else CampaignStatus.SCHEDULED
        )
        return replace(self, status=next_status, updated_at=now)

    def end(self, *, now: datetime) -> BannerCampaign:
        """`SCHEDULED | RUNNING | PAUSED -> ENDED`. Called either by an operator's explicit
        early-stop (`endCampaign`) or by `CampaignScheduleSweepWorker` when `schedule.end` is
        reached -- both emit the SAME `BannerCampaignEnded` event (ADR-0004), since the frozen
        catalogue draws no distinction between the two triggers."""
        if self.status not in _ENDABLE_STATES:
            raise IllegalCampaignStateTransitionError("end", self.status.value)
        return replace(self, status=CampaignStatus.ENDED, updated_at=now)

    def mark_creative_status(self, status: CreativeStatus, *, now: datetime) -> BannerCampaign:
        """Applies media's own `MediaAssetReady`/`MediaAssetRejected` projection (X-06) onto this
        campaign's cached snapshot -- callable in any status (mirrors `ImageAttachment`'s own
        redelivery-safe, always-applicable projection; a late quarantine on an already-RUNNING
        campaign must still be reflected so the next serve-time read excludes it, I-20)."""
        return replace(self, creative_status=status, updated_at=now)
