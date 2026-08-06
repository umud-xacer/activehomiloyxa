"""ads -- `CampaignEligibilityPolicy` (DDD Sec 9 I-21, applied together with media's own I-20).

I-21 (quoted verbatim): "A BannerCampaign serves only within its schedule, matching targeting, in
its configured slot, while its booking entitlement is active." Exactly four clauses -- schedule,
targeting, slot, entitlement-active -- implemented here as four named checks and nothing else.

I-20 (media's own invariant, applied cross-context): "A stored MediaAsset is image-typed,
malware-clean, and EXIF/GPS-free; quarantined assets are never delivered." This policy enforces
the "never delivered" half against a campaign's cached `creative_status` as a FIFTH, separately
named check -- deliberately not folded into `is_eligible_under_i21` so a test/reader never mistakes
it for something I-21's own text says. See `ads/README.md` "Design notes" for why this split
exists rather than a single five-clause `is_eligible` (the task brief's own illustrative example
conflates the two; I-21's literal text does not name creative status at all).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ads.domain.banner_campaign import BannerCampaign
from ads.domain.value_objects import CreativeStatus


class CampaignEligibilityPolicy:
    @staticmethod
    def is_eligible_under_i21(
        campaign: BannerCampaign,
        *,
        requested_slot_key: str,
        requested_category_id: UUID | None,
        requested_geo: str | None,
        requested_language: str | None,
        entitlement_active: bool,
        now: datetime,
    ) -> bool:
        """The four I-21 clauses, in the invariant's own order. `requested_slot_key` is checked
        explicitly here even though the caller typically already filtered by slot at the query
        layer -- domain-layer correctness must not depend on an infrastructure query being right
        (Playbook Sec 6: guard the invariant in the domain object, not only in SQL)."""
        within_schedule = campaign.schedule.covers(now)
        matching_targeting = campaign.targeting.matches(
            category_id=requested_category_id,
            geo=requested_geo,
            language=requested_language,
        )
        in_configured_slot = campaign.slot_key == requested_slot_key
        return within_schedule and matching_targeting and in_configured_slot and entitlement_active

    @staticmethod
    def is_eligible_under_i20(campaign: BannerCampaign) -> bool:
        """The separate creative-cleanliness clause (I-20, cross-context)."""
        return campaign.creative_status is CreativeStatus.CLEAN

    @classmethod
    def is_servable(
        cls,
        campaign: BannerCampaign,
        *,
        requested_slot_key: str,
        requested_category_id: UUID | None,
        requested_geo: str | None,
        requested_language: str | None,
        entitlement_active: bool,
        now: datetime,
    ) -> bool:
        """Both gates together -- what `BannerServingUseCases.serve_banner` actually filters on."""
        return cls.is_eligible_under_i21(
            campaign,
            requested_slot_key=requested_slot_key,
            requested_category_id=requested_category_id,
            requested_geo=requested_geo,
            requested_language=requested_language,
            entitlement_active=entitlement_active,
            now=now,
        ) and cls.is_eligible_under_i20(campaign)
