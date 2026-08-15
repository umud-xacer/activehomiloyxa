"""profiles -- typed domain exceptions, one per invariant violated (Playbook Sec 6). Mirrors
`catalog.domain.exceptions`/`billing.domain.exceptions`'s style. `interfaces/errors.py` maps
each of these to a `contracts.errors.Problem` (closed `ErrorCode` vocabulary).
"""

from __future__ import annotations

from uuid import UUID


class ProfilesDomainError(Exception):
    """Base for every typed exception raised by profiles' domain/ layer."""


# --- BusinessProfile lifecycle (ProfileStatus: Created -> Active -> Archived) --------------------


class IllegalProfileStatusTransitionError(ProfilesDomainError):
    """Attempted a transition method from a `ProfileStatus` it does not accept."""

    def __init__(self, transition: str, current: str) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} a business profile in status {current}")


class PortfolioItemLimitExceededError(ProfilesDomainError):
    """Physical DB `ck (position BETWEEN 1 AND 50)`: a business profile may hold at most 50
    portfolio items."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"a business profile may hold at most {limit} portfolio items")


class PortfolioItemNotFoundError(ProfilesDomainError):
    def __init__(self, item_id: UUID) -> None:
        self.item_id = item_id
        super().__init__(f"no portfolio item {item_id} on this business profile")


# --- promo video (landing-page promo-video business rule, additive) ------------------------------


class PromoVideoLimitExceededError(ProfilesDomainError):
    """A business profile may hold at most `MAX_PROMO_VIDEOS` promo videos."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"a business profile may hold at most {limit} promo videos")


class PromoVideoNotFoundError(ProfilesDomainError):
    def __init__(self, media_asset_id: UUID) -> None:
        self.media_asset_id = media_asset_id
        super().__init__(f"no promo video {media_asset_id} on this business profile")


# --- onboarding / trial (ADR-0010) -----------------------------------------------------------


class OnboardingAlreadyCompletedError(ProfilesDomainError):
    """`complete_onboarding` is a one-time transition (mirrors `issue_badge`'s "no setter, no
    alternate path" discipline) -- a profile that already has `onboarding_completed_at` set
    cannot start a second trial by calling it again."""

    def __init__(self, profile_id: UUID) -> None:
        self.profile_id = profile_id
        super().__init__(f"business profile {profile_id} has already completed onboarding")


class OnboardingIncompleteError(ProfilesDomainError):
    """`complete_onboarding`'s own precondition: the mandatory landing-page fields (name, at
    least one phone, logo, description, address, at least one portfolio item) must already be
    set on the aggregate before it will start the trial -- named per the first missing field so
    the frontend wizard can point the owner at exactly what to fill in next."""

    def __init__(self, missing_field: str) -> None:
        self.missing_field = missing_field
        super().__init__(f"cannot complete onboarding: missing required field {missing_field!r}")


# --- I-13: the badge-issuance guard --------------------------------------------------------------


class BadgeNotIssuableWithoutApprovedCaseError(ProfilesDomainError):
    """I-13: "A VerifiedBadge exists only from an approved case." Raised by
    `verification_case.ApprovedVerificationProof.from_case` whenever the given `VerificationCase`
    is not `APPROVED` -- the ONE place `BusinessProfile.issue_badge` will accept a caller's
    proof-of-approval from, making "no code path issues a badge without an approved case" true
    structurally (the same discipline `billing.domain.entitlement.
    EntitlementActivationWithoutPaymentError` establishes for I-14)."""

    def __init__(self, case_id: UUID, case_status: str) -> None:
        self.case_id = case_id
        self.case_status = case_status
        super().__init__(
            f"cannot issue a badge from case {case_id}: case status is {case_status!r}, not "
            "APPROVED"
        )


class IllegalBadgeTransitionError(ProfilesDomainError):
    """Attempted a badge transition (`issue_badge`/`expire_badge`/`revoke_badge`) the current
    badge sub-state does not accept (e.g. expiring a badge that was never issued, or one already
    `EXPIRED`/`REVOKED`)."""

    def __init__(self, transition: str, current: str | None) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} a badge currently in status {current!r}")


# --- VerificationCase lifecycle (CaseStatus: Requested -> InReview -> Approved | Rejected) -------


class IllegalVerificationCaseStateTransitionError(ProfilesDomainError):
    """Attempted a transition method from a `CaseStatus` it does not accept."""

    def __init__(self, transition: str, current: str) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} a verification case in status {current}")


class TerminalVerificationCaseError(ProfilesDomainError):
    """ "Approved and Rejected are TERMINAL and IMMUTABLE ... never edited after decision" (P-11
    scope). Raised by every mutating `VerificationCase` method (`mark_in_review`/`decide`/
    `add_document`) once `status` is `APPROVED` or `REJECTED` -- distinct from
    `IllegalVerificationCaseStateTransitionError` so callers/tests can assert terminal-immutability
    specifically, not merely "some illegal transition was attempted"."""

    def __init__(self, case_id: UUID, case_status: str) -> None:
        self.case_id = case_id
        self.case_status = case_status
        super().__init__(
            f"verification case {case_id} is terminal ({case_status}) and cannot be modified"
        )


class NoDocumentsSubmittedError(ProfilesDomainError):
    """I-12: "A VerificationCase requires submitted image documents ... before entering the
    queue." Raised by `VerificationCase.create` if given zero documents."""


class DuplicateDocumentPositionError(ProfilesDomainError):
    def __init__(self) -> None:
        super().__init__("submitted document positions must be unique and contiguous from 1")
