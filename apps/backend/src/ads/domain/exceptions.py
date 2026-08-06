"""ads -- typed domain exceptions, one per invariant violated (Playbook Sec 6). Mirrors
`billing.domain.exceptions`'s style. `interfaces/errors.py` maps each of these to a
`contracts.errors.Problem` (closed `ErrorCode` vocabulary).
"""

from __future__ import annotations


class AdsDomainError(Exception):
    """Base for every typed exception raised by ads' domain/ layer."""


class IllegalCampaignStateTransitionError(AdsDomainError):
    """Attempted a transition method from a `CampaignStatus` it does not accept (Physical DB
    Design's own `ck_banner_campaign_status` CHECK vocabulary: DRAFT/SCHEDULED/RUNNING/PAUSED/
    ENDED)."""

    def __init__(self, transition: str, current: str) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} a campaign in status {current}")


class InvalidScheduleError(AdsDomainError):
    """`Schedule`'s own construction invariant (FR-BANNER-002): `end` must be strictly after
    `start`."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"invalid Schedule: {reason}")


class CampaignNotEligibleError(AdsDomainError):
    """I-21: "A BannerCampaign serves only within its schedule, matching targeting, in its
    configured slot, while its booking entitlement is active." Raised by `CampaignUseCases.
    schedule_campaign`/`resume_campaign` when the campaign fails one of I-21's four clauses (or
    I-20's separate creative-clean clause) at the moment an operator tries to make it servable --
    never raised by the read-only serve path itself, which simply excludes an ineligible campaign
    from selection rather than erroring."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"campaign is not eligible to serve: {reason}")
