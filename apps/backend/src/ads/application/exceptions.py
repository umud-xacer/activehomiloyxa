"""ads/application -- typed application-level exceptions (not-found / cross-context resolution
failures). Mirrors `billing.application.exceptions`'s style."""

from __future__ import annotations

from uuid import UUID


class AdsApplicationError(Exception):
    """Base for every typed exception raised by ads' application/ layer."""


class CampaignNotFoundError(AdsApplicationError):
    def __init__(self, campaign_id: UUID) -> None:
        self.campaign_id = campaign_id
        super().__init__(f"no BannerCampaign with id {campaign_id}")


class SlotNotFoundError(AdsApplicationError):
    """No published `PlacementSlotDefinition` with the given `SlotKey` (`configuration`'s own
    admin-authored inventory, FR-BANNER-001 -- ads never creates one, only references it)."""

    def __init__(self, slot_key: str) -> None:
        self.slot_key = slot_key
        super().__init__(f"no published placement slot with key {slot_key!r}")


class EntitlementNotFoundError(AdsApplicationError):
    """No `BANNER_SLOT_BOOKING` entitlement with this id in ads' own local projection (I-15/I-21)
    -- either it was never activated, or `EntitlementActivated` has not yet been projected."""

    def __init__(self, entitlement_id: UUID) -> None:
        self.entitlement_id = entitlement_id
        super().__init__(f"no active BANNER_SLOT_BOOKING entitlement with id {entitlement_id}")
