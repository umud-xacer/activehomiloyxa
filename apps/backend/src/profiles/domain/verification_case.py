"""profiles -- the `VerificationCase` aggregate (DDD Sec 5.2 `AR: VerificationCase [P]`).
Persistence-ignorant, mirrors `catalog.domain.listing.Listing`'s style exactly: frozen dataclass,
every transition returns a new instance via `dataclasses.replace`, guarded by a typed exception
raised before the replace.

Terminal-immutability (P-11 scope: "Approved and Rejected are TERMINAL and IMMUTABLE ... never
edited after decision") is enforced procedurally: every mutating method's FIRST check is
`_guard_not_terminal`, before any other validation -- there is no method on this class that can
touch a case once `status` is `APPROVED`/`REJECTED`, matching Physical DB's own guard-trigger
discipline for the same rule at the database layer (`catalog.domain.listing.Listing.delete`'s
"blocked at the database level" precedent, applied here at the domain layer instead since no
guard-trigger migration is part of this task -- see `infrastructure/migrations`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from profiles.domain.exceptions import (
    BadgeNotIssuableWithoutApprovedCaseError,
    DuplicateDocumentPositionError,
    IllegalVerificationCaseStateTransitionError,
    NoDocumentsSubmittedError,
    TerminalVerificationCaseError,
)
from profiles.domain.submitted_document import SubmittedDocument
from profiles.domain.value_objects import TERMINAL_CASE_STATUSES, CaseStatus, Decision
from shared_kernel import BusinessProfileId

MAX_DOCUMENTS = 20
"""No document specifies a limit; a conservative platform [P] ceiling (mirrors
`catalog.domain.listing.MAX_IMAGE_ATTACHMENTS`'s role as a fixed, non-configurable bound) so a
single case can never carry an unbounded document set."""


@dataclass(frozen=True)
class VerificationCase:
    id: UUID
    business_profile_id: BusinessProfileId
    entitlement_id: UUID
    """xref billing.entitlement -- the VerificationEligibility entitlement this case was granted
    against (I-12), captured once at `create` and never rebound."""
    status: CaseStatus
    sla_due_at: datetime
    """BRULE-05: "verification target SLA is defined and monitored (design phase sets the exact
    value)" -- this task's own design-phase value, `profiles.domain.policies.
    VERIFICATION_SLA_HOURS`, computed by the caller and passed in."""
    documents: tuple[SubmittedDocument, ...]
    decision: Decision | None
    created_at: datetime
    updated_at: datetime
    lock_version: int = 0

    # --- factory (FR-PROF-004, I-12) ------------------------------------------------------------

    @staticmethod
    def create(
        *,
        case_id: UUID,
        business_profile_id: BusinessProfileId,
        entitlement_id: UUID,
        documents: tuple[SubmittedDocument, ...],
        sla_due_at: datetime,
        now: datetime,
    ) -> VerificationCase:
        """I-12's own structural half: "requires submitted image documents ... before entering
        the queue" -- raises `NoDocumentsSubmittedError` if given none. The entitlement-active
        half of I-12 is the caller's responsibility (`application.VerificationUseCases.
        request_verification` checks the local eligibility projection before calling this) since
        that check needs a repository read, which a `@staticmethod` factory cannot perform."""
        if not documents:
            raise NoDocumentsSubmittedError()
        positions = sorted(document.position for document in documents)
        if positions != list(range(1, len(documents) + 1)):
            raise DuplicateDocumentPositionError()
        return VerificationCase(
            id=case_id,
            business_profile_id=business_profile_id,
            entitlement_id=entitlement_id,
            status=CaseStatus.REQUESTED,
            sla_due_at=sla_due_at,
            documents=documents,
            decision=None,
            created_at=now,
            updated_at=now,
        )

    # --- terminal-immutability guard -------------------------------------------------------------

    def _guard_not_terminal(self) -> None:
        if self.status in TERMINAL_CASE_STATUSES:
            raise TerminalVerificationCaseError(self.id, self.status.value)

    # --- reviewer workflow (FR-PROF-005, BRULE-05) ------------------------------------------------

    def mark_in_review(self, *, now: datetime) -> VerificationCase:
        """A reviewer claims the case from the queue. Legal from `REQUESTED` only -- `decide`
        below also accepts `REQUESTED` directly (a reviewer may approve/reject without a separate
        claim step; no OpenAPI operation exposes `mark_in_review` on its own, see
        `application.VerificationUseCases.claim_case`'s own docstring), so this method exists for
        reviewer-queue completeness ("claim" is named explicitly in P-11's own use-case list) even
        though `decide` does not require it as a precondition."""
        self._guard_not_terminal()
        if self.status is not CaseStatus.REQUESTED:
            raise IllegalVerificationCaseStateTransitionError("mark_in_review", self.status.value)
        return replace(self, status=CaseStatus.IN_REVIEW, updated_at=now)

    def decide(
        self, *, outcome: CaseStatus, reason: str | None, reviewer_user_id: UUID, now: datetime
    ) -> VerificationCase:
        """FR-PROF-005: "approve or reject a verification case, recording the outcome." Legal
        from `REQUESTED` or `IN_REVIEW` -- both are pre-decision states (DDD Sec 5.2's own
        `CaseStatus` VO: "Requested -> InReview -> Approved / Rejected", read as the *reviewer*
        need not have separately claimed the case first). `outcome` must be `APPROVED` or
        `REJECTED`; any other value is a caller bug, not a domain state to guard against here
        (the type itself is `CaseStatus`, not a free string) -- `application/` is the only caller
        and always passes one of the two."""
        self._guard_not_terminal()
        if self.status not in (CaseStatus.REQUESTED, CaseStatus.IN_REVIEW):
            raise IllegalVerificationCaseStateTransitionError("decide", self.status.value)
        decision = Decision(
            outcome=outcome, reason=reason, reviewer_user_id=reviewer_user_id, decided_at=now
        )
        return replace(self, status=outcome, decision=decision, updated_at=now)

    # --- documents (I-12/FR-PROF-003; media asset-status projection, X-06) -----------------------

    def remove_document_for_media_asset(
        self, media_asset_id: UUID, *, now: datetime
    ) -> VerificationCase:
        """Applies media's `MediaAssetRejected` projection (X-06): a quarantined document is
        removed from the case rather than merely flagged (Physical DB `submitted_document` has no
        status column to flip -- same reasoning as `PortfolioItem`'s own docstring). A no-op if
        the case holds no document for this asset (arrived late / already removed, redelivery-safe
        like `catalog.domain.listing.Listing.update_image_status`) OR if the case is terminal
        (terminal-immutability wins over cleanliness projection: "never edited after decision" is
        unconditional, so a rejection event arriving after approval/rejection is silently
        ignored, not applied -- the audit record stays exactly as decided)."""
        if self.status in TERMINAL_CASE_STATUSES:
            return self
        if not any(document.media_asset_id == media_asset_id for document in self.documents):
            return self
        remaining = tuple(d for d in self.documents if d.media_asset_id != media_asset_id)
        renumbered = tuple(
            replace(document, position=index + 1) for index, document in enumerate(remaining)
        )
        return replace(self, documents=renumbered, updated_at=now)


@dataclass(frozen=True)
class ApprovedVerificationProof:
    """I-13's structural guard: the ONLY way to construct one is `from_case`, which raises
    `BadgeNotIssuableWithoutApprovedCaseError` unless the given case's own `status` is `APPROVED`.
    `BusinessProfile.issue_badge` requires one of these as an argument -- there is no calling
    convention that reaches a `VALID` badge without an approved case in hand, the same "one
    constructor, no bypass" discipline `billing.domain.entitlement.EntitlementFactory.
    activate_from_paid_order` establishes for I-14."""

    case_id: UUID
    business_profile_id: BusinessProfileId
    entitlement_id: UUID

    @staticmethod
    def from_case(case: VerificationCase) -> ApprovedVerificationProof:
        if case.status is not CaseStatus.APPROVED:
            raise BadgeNotIssuableWithoutApprovedCaseError(case.id, case.status.value)
        return ApprovedVerificationProof(
            case_id=case.id,
            business_profile_id=case.business_profile_id,
            entitlement_id=case.entitlement_id,
        )
