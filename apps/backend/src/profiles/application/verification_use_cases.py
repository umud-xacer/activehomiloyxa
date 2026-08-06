"""profiles/application -- `VerificationUseCases` (Task P-11): submit/request verification
(I-12), reviewer claim/decide (I-13), re-verification, and the entitlement/media asset-status
projections. This is the module's trust core: `decide_verification` is the ONLY call path in the
entire codebase that can move a `BusinessProfile.badge` to `VALID` (via
`profiles.domain.verification_case.ApprovedVerificationProof`, I-13's structural guard) -- every
other method here queries or records facts around it, never bypasses it.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from contracts.events.profiles import (
    BusinessVerified,
    VerificationRejected,
    VerificationRequested,
)
from profiles.application.exceptions import (
    NotProfileOwnerError,
    ProfileNotFoundError,
    VerificationCaseNotFoundError,
    VerificationNotEligibleError,
)
from profiles.application.ports import (
    BusinessProfileRepository,
    MediaAssetReaderPort,
    VerificationCaseRepository,
    VerificationEligibilityRepository,
    VerificationEligibilitySnapshot,
)
from profiles.domain import (
    ApprovedVerificationProof,
    CaseStatus,
    VerificationCase,
    compute_sla_due_at,
    order_queue,
)
from profiles.domain.submitted_document import SubmittedDocument
from shared_kernel import BusinessProfileId, OutboxPort, UserId


class VerificationUseCases:
    def __init__(
        self,
        *,
        profiles: BusinessProfileRepository,
        cases: VerificationCaseRepository,
        eligibility: VerificationEligibilityRepository,
        media: MediaAssetReaderPort,
        outbox: OutboxPort,
    ) -> None:
        self._profiles = profiles
        self._cases = cases
        self._eligibility = eligibility
        self._media = media
        self._outbox = outbox

    # --- request (FR-PROF-003/004, I-12) ----------------------------------------------------------

    async def request_verification(
        self,
        profile_id: BusinessProfileId,
        *,
        owner_user_id: UserId,
        entitlement_id: UUID,
        documents: list[tuple[UUID, str]],
        now: datetime,
    ) -> VerificationCase:
        """`documents` is a list of `(media_asset_id, document_kind)` pairs, in submission
        order."""
        profile = await self._profiles.get_by_id(profile_id)
        if profile is None:
            raise ProfileNotFoundError(profile_id)
        if profile.owner_user_id != owner_user_id:
            raise NotProfileOwnerError(profile_id)

        eligibility = await self._eligibility.get_active_for_profile(profile_id, now=now)
        if eligibility is None or eligibility.entitlement_id != entitlement_id:
            raise VerificationNotEligibleError(profile_id)

        submitted_documents = tuple(
            SubmittedDocument(
                id=uuid4(),
                media_asset_id=media_asset_id,
                document_kind=document_kind,
                position=index + 1,
                created_at=now,
            )
            for index, (media_asset_id, document_kind) in enumerate(documents)
        )
        case = VerificationCase.create(
            case_id=uuid4(),
            business_profile_id=profile_id,
            entitlement_id=eligibility.entitlement_id,
            documents=submitted_documents,
            sla_due_at=compute_sla_due_at(now=now),
            now=now,
        )
        await self._cases.add(case)
        await self._outbox.append(
            VerificationRequested(
                event_id=uuid4(),
                occurred_at=now,
                actor=owner_user_id.value,
                aggregate_type="VerificationCase",
                aggregate_id=case.id,
                payload={
                    "verificationCaseId": str(case.id),
                    "businessProfileId": str(profile_id.value),
                },
            )
        )
        return case

    # --- query -----------------------------------------------------------------------------------

    async def get_current_case(
        self, profile_id: BusinessProfileId, *, owner_user_id: UserId
    ) -> VerificationCase:
        profile = await self._profiles.get_by_id(profile_id)
        if profile is None:
            raise ProfileNotFoundError(profile_id)
        if profile.owner_user_id != owner_user_id:
            raise NotProfileOwnerError(profile_id)
        case = await self._cases.get_current_for_profile(profile_id)
        if case is None:
            raise VerificationCaseNotFoundError(profile_id.value)
        return case

    async def list_queue(
        self, *, status: CaseStatus | None, cursor: str | None, limit: int
    ) -> tuple[list[VerificationCase], str | None]:
        """Reviewer-only (`profiles:verification:review`, checked at the router/composition-root
        layer -- see `interfaces/di.py::get_acting_reviewer`). `QueueOrderingPolicy` (earliest
        SLA deadline first) is applied to the fetched page; the repository itself orders by
        `sla_due_at` too (defence in depth, matching `catalog.application.ListingUseCases`'s own
        "the rule is owned by the domain method, re-derived defensively" style) -- see
        `profiles.domain.policies.order_queue`."""
        cases, next_cursor = await self._cases.list_queue(status=status, cursor=cursor, limit=limit)
        return order_queue(cases), next_cursor

    # --- reviewer workflow (FR-PROF-005, I-13) -----------------------------------------------------

    async def claim_case(self, case_id: UUID, *, now: datetime) -> VerificationCase:
        """ "claim" from P-11's own use-case list; no OpenAPI operation exposes it on its own (see
        `profiles.domain.verification_case.VerificationCase.mark_in_review`'s own docstring) --
        reviewer-only, same permission gate as `list_queue`/`decide_verification`."""
        case = await self._cases.get_by_id(case_id)
        if case is None:
            raise VerificationCaseNotFoundError(case_id)
        claimed = case.mark_in_review(now=now)
        return await self._cases.save(claimed)

    async def decide_verification(
        self,
        case_id: UUID,
        *,
        reviewer_user_id: UUID,
        outcome: CaseStatus,
        reason: str | None,
        now: datetime,
    ) -> VerificationCase:
        """I-13's only call path to a `VALID` badge. `outcome` must be `APPROVED` or `REJECTED`
        (the router only ever passes one of the two, translated from `VerificationDecisionRequest.
        outcome`)."""
        case = await self._cases.get_by_id(case_id)
        if case is None:
            raise VerificationCaseNotFoundError(case_id)
        decided = case.decide(
            outcome=outcome, reason=reason, reviewer_user_id=reviewer_user_id, now=now
        )
        saved_case = await self._cases.save(decided)

        if outcome is CaseStatus.REJECTED:
            await self._outbox.append(
                VerificationRejected(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=reviewer_user_id,
                    aggregate_type="VerificationCase",
                    aggregate_id=saved_case.id,
                    payload={
                        "verificationCaseId": str(saved_case.id),
                        "businessProfileId": str(saved_case.business_profile_id.value),
                        "reason": reason,
                    },
                )
            )
            return saved_case

        # APPROVED: I-13's structural guard -- ApprovedVerificationProof.from_case raises unless
        # saved_case.status is APPROVED (it always is here, `case.decide` just set it).
        proof = ApprovedVerificationProof.from_case(saved_case)
        entitlement_snapshot = await self._eligibility.get_by_entitlement_id(proof.entitlement_id)
        valid_until = entitlement_snapshot.valid_until if entitlement_snapshot is not None else None
        if valid_until is None:
            # The entitlement projection that gated `request_verification` is no longer resolvable
            # (should not happen given I-12's own precondition already proved it existed) -- fails
            # closed rather than issuing a badge with a guessed validity period (Playbook Sec 6).
            raise VerificationNotEligibleError(proof.business_profile_id)

        profile = await self._profiles.get_by_id(proof.business_profile_id)
        if profile is None:
            raise ProfileNotFoundError(proof.business_profile_id)
        badged = profile.issue_badge(proof=proof, valid_until=valid_until, now=now)
        await self._profiles.save(badged)

        await self._outbox.append(
            BusinessVerified(
                event_id=uuid4(),
                occurred_at=now,
                actor=reviewer_user_id,
                aggregate_type="VerificationCase",
                aggregate_id=saved_case.id,
                payload={
                    "verificationCaseId": str(saved_case.id),
                    "businessProfileId": str(proof.business_profile_id.value),
                },
            )
        )
        return saved_case

    # --- entitlement projection (X-03) -------------------------------------------------------------

    async def apply_entitlement_projection(self, snapshot: VerificationEligibilitySnapshot) -> None:
        """Idempotent upsert of a projected billing entitlement (I-12) -- called by
        `infrastructure.event_projection`, wrapped in its own `idempotent_consume` ledger check
        against the *producing* billing event's own `event_id`."""
        await self._eligibility.upsert(snapshot)

    # --- media asset-status projection (X-06) -----------------------------------------------------

    async def apply_document_media_rejection(self, media_asset_id: UUID, *, now: datetime) -> None:
        """`MediaAssetRejected` projection: removes the submitted document referencing this
        asset, if any and if the case is not terminal (see `VerificationCase.
        remove_document_for_media_asset`'s own docstring)."""
        case = await self._cases.get_by_document_media_asset_id(media_asset_id)
        if case is None:
            return
        updated = case.remove_document_for_media_asset(media_asset_id, now=now)
        if updated is case:
            return
        await self._cases.save(updated)
