"""profiles (BC-02) domain events -- DDD Sec 6, the authoritative v1 event catalogue.

STATUS: frozen (Task P-01), amended by ADR-0010 (2026-08-14, `TrialSubscriptionStarted`/
`TrialSubscriptionEnded`) and ADR-0012 (2026-08-25, `BusinessProfileApproved`/
`BusinessProfileRejected` -- the B2B Directory professional-upgrade task's registration-approval
gate) -- see those ADRs for why these rows exist outside the original DDD Sec 6 table. Schema
only: each class is the shared envelope (`shared_kernel.EventEnvelope`) with `event_type` pinned
to its own past-tense name. No publishing logic, no handlers -- that is outbox/adapter work for a
later task. Do not add an event here that is not a row in DDD Sec 6 for this context (or covered
by a merged ADR like ADR-0010/ADR-0012); do not remove one either without an ADR (Playbook Sec 18)
amending the Domain Model.
"""

from __future__ import annotations

from typing import Literal

from shared_kernel import EventEnvelope


class BusinessProfileCreated(EventEnvelope):
    """Emitted when: Profile of one of eight types created.

    Principal consumers: Analytics.
    """

    event_type: Literal["BusinessProfileCreated"] = "BusinessProfileCreated"


class VerificationRequested(EventEnvelope):
    """Emitted when: Case enters reviewer queue.

    Principal consumers: Administration (queue), Notifications.
    """

    event_type: Literal["VerificationRequested"] = "VerificationRequested"


class BusinessVerified(EventEnvelope):
    """Emitted when: Case approved, badge issued.

    Principal consumers: Search (badge flag), Notifications, Analytics, Audit.
    """

    event_type: Literal["BusinessVerified"] = "BusinessVerified"


class VerificationRejected(EventEnvelope):
    """Emitted when: Case rejected with reason.

    Principal consumers: Notifications, Audit.
    """

    event_type: Literal["VerificationRejected"] = "VerificationRejected"


class VerifiedBadgeExpired(EventEnvelope):
    """Emitted when: Validity period ends.

    Principal consumers: Search, Notifications (re-verification prompt).
    """

    event_type: Literal["VerifiedBadgeExpired"] = "VerifiedBadgeExpired"


class TrialSubscriptionStarted(EventEnvelope):
    """ADR-0010. Emitted when: a LEGAL_ENTITY owner completes the mandatory onboarding wizard
    and the 5-day free trial begins.

    Principal consumers: Catalog (restores/keeps visible the profile's own listings).
    """

    event_type: Literal["TrialSubscriptionStarted"] = "TrialSubscriptionStarted"


class TrialSubscriptionEnded(EventEnvelope):
    """ADR-0010. Emitted when: the trial-expiry sweep worker finds a profile whose
    `trial_ends_at` has passed with no paid subscription having superseded it.

    Principal consumers: Catalog (suspends the profile's own listings from public search).
    """

    event_type: Literal["TrialSubscriptionEnded"] = "TrialSubscriptionEnded"


class BusinessProfileApproved(EventEnvelope):
    """ADR-0012. Emitted when: a reviewer approves a `PENDING_REVIEW` business profile
    (`ProfileUseCases.decide_registration`, outcome=APPROVED) -- the profile becomes `ACTIVE` and
    its public landing page/directory listing become reachable.

    Principal consumers: Catalog (reactivates the profile's own listings suspended for pending
    review, mirroring `TrialSubscriptionStarted`'s own reason).
    """

    event_type: Literal["BusinessProfileApproved"] = "BusinessProfileApproved"


class BusinessProfileRejected(EventEnvelope):
    """ADR-0012. Emitted when: a reviewer rejects a `PENDING_REVIEW` business profile
    (`ProfileUseCases.decide_registration`, outcome=REJECTED) -- the profile's public landing
    page/directory listing stay unreachable until the owner edits and is re-reviewed.

    Principal consumers: Catalog (keeps/suspends the profile's own listings), Notifications.
    """

    event_type: Literal["BusinessProfileRejected"] = "BusinessProfileRejected"
