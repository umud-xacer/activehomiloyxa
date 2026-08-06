"""ads/application -- ports (Task P-14). Abstract surface only (typing.Protocol);
`infrastructure/` implements every one of these, never the reverse (Clean Architecture rule 4).

Every cross-module read is shaped as ads' *own* narrow Protocol/dataclass here -- never a
`configuration.interfaces`/`media.interfaces` type imported directly into `application/` -- the
same discipline `billing.application.ports.ProductDefinitionReaderPort`/
`ProductDefinitionSnapshot` already set (P-09). The concrete adapters bridging to
`configuration.interfaces`/`media.interfaces` live in `ads/infrastructure/`, wired only at the
composition root (`cross-module-ads`, tools/importlinter.cfg).

`billing` is fully forbidden by `cross-module-ads` (unlike `configuration`/`media`, which ads may
import via their `interfaces/` packages directly) -- `EntitlementProjectionRepository` is
therefore not a live cross-module read at all, but ads' own local projection table, populated
event-only by `infrastructure.event_projection.handle_entitlement_event`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from ads.domain import BannerCampaign, CampaignStatus, CreativeStatus


class BannerCampaignRepository(Protocol):
    """One repository per aggregate root (`BannerCampaign`) -- Clean Architecture rule 2."""

    async def get_by_id(self, campaign_id: UUID) -> BannerCampaign | None: ...

    async def add(self, campaign: BannerCampaign) -> None: ...

    async def save(self, campaign: BannerCampaign) -> BannerCampaign:
        """Returns the persisted aggregate with its post-flush `lock_version` -- callers must use
        the returned value (mirrors `billing.application.ports.OrderRepository.save`)."""
        ...

    async def list_for_operator(
        self,
        *,
        status: CampaignStatus | None,
        slot_key: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[BannerCampaign], str | None]:
        """Backs `listCampaigns` -- unscoped by any single operator (a shared operator queue,
        mirrors `InvoiceRepository.list_all`'s own admin-queue shape, not a purchaser-scoped
        list)."""
        ...

    async def list_candidates_for_serve(self, *, slot_key: str) -> tuple[BannerCampaign, ...]:
        """Backs `serveBanner`. Pre-filtered to `SCHEDULED`/`RUNNING` campaigns in this slot only
        (the cheap, indexed half of I-21's "configured slot" + "within schedule" clauses) --
        `CampaignEligibilityPolicy` still re-checks both in full against the returned rows
        (Playbook Sec 6: the domain object, not the query, is the source of truth for the
        invariant). Ordered by `priority` descending, so the use case can select the first
        eligible row without re-sorting."""
        ...

    async def list_by_creative_media_asset_id(
        self, media_asset_id: UUID
    ) -> tuple[BannerCampaign, ...]:
        """Backs `infrastructure.event_projection.handle_media_event`'s creative-status
        projection (X-06, mirrors `catalog.infrastructure.event_projection.handle_media_event`'s
        own `get_by_image_media_asset_id` lookup) -- every campaign currently referencing this
        creative, regardless of status (a late quarantine must still update an ENDED campaign's
        own record, even though it can no longer serve)."""
        ...

    async def list_due_to_start(self, *, now: datetime) -> tuple[BannerCampaign, ...]:
        """Backs `CampaignUseCases.sweep_schedule_transitions`: every `SCHEDULED` campaign whose
        `schedule.start` has arrived."""
        ...

    async def list_due_to_end(self, *, now: datetime) -> tuple[BannerCampaign, ...]:
        """Backs `CampaignUseCases.sweep_schedule_transitions`: every still-live
        (`SCHEDULED`/`RUNNING`/`PAUSED`) campaign whose `schedule.end` has passed."""
        ...


@dataclass(frozen=True)
class SlotSnapshot:
    """ads' own narrow read shape for a published `PlacementSlotDefinition`
    (`configuration.domain.content.PlacementSlotDefinitionContent`) -- not a
    `configuration.interfaces` DTO, mirroring `billing.application.ports.
    ProductDefinitionSnapshot`'s exact role."""

    head_id: UUID
    version_id: UUID
    slot_key: str


class PlacementSlotReaderPort(Protocol):
    """Reads the published `PlacementSlotDefinition` (BC-04, FR-BANNER-001 -- authored entirely
    in `configuration`, never here). The concrete adapter calls `configuration.interfaces.ports.
    ConfigurationPort.list_config_heads`/`get_config_version` only -- never `configuration.
    domain`/`application`/`infrastructure` (`cross-module-ads`)."""

    async def get_slot_by_key(self, slot_key: str) -> SlotSnapshot | None: ...


class CreativeReaderPort(Protocol):
    """Reads a `MediaAssetRef`'s current `scan_status` (I-20). The concrete adapter calls
    `media.interfaces.ports.MediaIntakePort.get_media` only -- never `media.domain`/
    `application`/`infrastructure` (`cross-module-ads`). Called synchronously only at operator
    admin actions (create/update/schedule/resume) -- NEVER at serve time, which reads only the
    locally cached `BannerCampaign.creative_status` (fast, no cross-module call)."""

    async def get_creative_status(self, media_asset_id: UUID) -> CreativeStatus: ...


@dataclass(frozen=True)
class EntitlementSnapshot:
    """ads' own local projection row for a `BANNER_SLOT_BOOKING` billing Entitlement (I-15/I-21)
    -- populated event-only from `EntitlementActivated`/`Expired`/`Revoked`, never a live read of
    billing (`billing` is fully forbidden by `cross-module-ads`, unlike `configuration`/`media`)."""

    entitlement_id: UUID
    target_id: UUID
    """The booked `PlacementSlotDefinition`'s head id (billing's own `Order.targetId` for a
    `SLOT_BOOKING` order) -- must equal the campaign's own `placement_slot_id` for I-21's
    "configured slot" half of the entitlement check."""
    valid_from: datetime
    valid_until: datetime
    activation_state: str
    """`ACTIVE` | `EXPIRED` | `REVOKED` -- billing's own closed `ActivationState` vocabulary,
    carried verbatim rather than re-declared as a duplicate enum (the value never leaves this
    dataclass as anything but a string comparison)."""

    def is_active(self, *, now: datetime) -> bool:
        return self.activation_state == "ACTIVE" and self.valid_from <= now < self.valid_until


class EntitlementProjectionRepository(Protocol):
    """ads' own local projection table -- NOT a cross-module port (no adapter implements this
    against `billing.interfaces`; `billing` is fully forbidden by `cross-module-ads`). Populated
    exclusively by `infrastructure.event_projection.handle_entitlement_event`."""

    async def get_by_id(self, entitlement_id: UUID) -> EntitlementSnapshot | None: ...

    async def upsert(self, snapshot: EntitlementSnapshot) -> None:
        """Full-shape insert/replace -- used for `EntitlementActivated`, whose payload carries
        `validFrom`/`validUntil`."""
        ...

    async def mark_state(self, entitlement_id: UUID, *, activation_state: str) -> None:
        """Partial update for `EntitlementExpired`/`EntitlementRevoked`, whose payload
        (`billing.application.entitlement_use_cases._entitlement_lifecycle_payload`) carries no
        `validFrom`/`validUntil` -- a no-op if the row doesn't exist yet (the redelivery-ordering
        edge case of a withdrawal event arriving before its own activation was ever projected)."""
        ...
