"""moderation/application -- `ModerationUseCases` (Task P-12): report intake, automated flagging,
reviewer claim/resolve, and queue query. `resolve_case` is the module's central use case: it
resolves the `ModerationCase` (one aggregate, one transaction, its own outbox event -- DB
Architecture Sec 1.3), THEN dispatches the already-decided verb to its target module via
`ModerationActionService` as a SEPARATE, eventually-consistent operation (X-04: "these are
compensations, not cascades... each target records its own transition and its own audit trail").
A target-command failure never un-resolves the case -- the moderation FACT is authoritative
regardless of downstream delivery, the same reasoning `profiles.application.
VerificationUseCases.decide_verification` documents for its own two-phase commit->react shape.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from contracts.events.moderation import ModerationActionTaken
from moderation.application.action_service import ModerationActionService
from moderation.application.exceptions import ModerationCaseNotFoundError
from moderation.application.ports import ModerationCaseRepository
from moderation.domain import (
    CaseStatus,
    ModerationCase,
    ResolutionAction,
    SubjectType,
    order_queue,
)
from moderation.domain.value_objects import Subject
from shared_kernel import OutboxPort


class ModerationUseCases:
    def __init__(
        self,
        *,
        cases: ModerationCaseRepository,
        action_service: ModerationActionService,
        outbox: OutboxPort,
    ) -> None:
        self._cases = cases
        self._action_service = action_service
        self._outbox = outbox

    # --- report intake (FR-MOD-001, FR-MSG-005) ---------------------------------------------------

    async def submit_report(
        self,
        *,
        subject_type: SubjectType,
        subject_id: UUID,
        reporter_user_id: UUID,
        reason: str,
        now: datetime,
    ) -> ModerationCase:
        """Consumes messaging's real `ContentReported` event (already published by `messaging.
        application.report_use_cases.ReportUseCases.create_report`, Task P-10) -- see
        `infrastructure.event_projection.handle_content_reported`. "A report opens or attaches to
        a ModerationCase" (P-12 scope): a second report against a subject that already has a
        non-terminal case attaches (returns the existing case unchanged) rather than opening a
        duplicate."""
        existing = await self._cases.get_open_or_in_review_for_subject(subject_type, subject_id)
        if existing is not None:
            return existing
        case = ModerationCase.open_from_report(
            case_id=uuid4(),
            subject=Subject(subject_type=subject_type, subject_id=subject_id),
            reporter_user_id=reporter_user_id,
            reason=reason,
            now=now,
        )
        await self._cases.add(case)
        return case

    # --- automated flagging (FR-MOD-002) ------------------------------------------------------------

    async def auto_flag(
        self,
        *,
        subject_type: SubjectType,
        subject_id: UUID,
        rule_key: str,
        now: datetime,
    ) -> ModerationCase:
        """Consumes catalog's real `ListingFlagged` event (already published by `catalog.
        application.listing_use_cases.ListingUseCases`'s own duplicate-detection flow, Task P-07)
        -- see `infrastructure.event_projection.handle_listing_flagged`. The FlaggingService
        (DDD Sec 5.11) is realised entirely as this reactive consumer: the rule EVALUATION happens
        in whichever context owns the content and can read configuration (moderation itself
        cannot -- SAD Sec 8.1's own moderation row permits `shared_kernel` only); moderation's own
        role is to open/attach the case once content has already been flagged (see
        `moderation/README.md` "The FlaggingService is reactive-only")."""
        existing = await self._cases.get_open_or_in_review_for_subject(subject_type, subject_id)
        if existing is not None:
            return existing
        case = ModerationCase.open_from_flag(
            case_id=uuid4(),
            subject=Subject(subject_type=subject_type, subject_id=subject_id),
            rule_key=rule_key,
            now=now,
        )
        await self._cases.add(case)
        return case

    # --- query (FR-MOD-005) -------------------------------------------------------------------------

    async def get_case(self, case_id: UUID) -> ModerationCase:
        case = await self._cases.get_by_id(case_id)
        if case is None:
            raise ModerationCaseNotFoundError(case_id)
        return case

    async def list_queue(
        self,
        *,
        status: CaseStatus | None,
        subject_type: SubjectType | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ModerationCase], str | None]:
        """Reviewer-only (`moderation:case:review`, checked at the router/composition-root layer
        -- see `interfaces/di.py::get_acting_moderator`). `QueueOrderingPolicy` is applied to the
        fetched page (defence in depth, matching `profiles.application.VerificationUseCases.
        list_queue`'s own precedent)."""
        cases, next_cursor = await self._cases.list_queue(
            status=status, subject_type=subject_type, cursor=cursor, limit=limit
        )
        return order_queue(cases), next_cursor

    # --- reviewer workflow (FR-MOD-003/004) ----------------------------------------------------------

    async def claim_case(self, case_id: UUID, *, now: datetime) -> ModerationCase:
        case = await self.get_case(case_id)
        claimed = case.claim(now=now)
        return await self._cases.save(claimed)

    async def resolve_case(
        self,
        case_id: UUID,
        *,
        action: ResolutionAction,
        note: str | None,
        moderator_user_id: UUID,
        now: datetime,
    ) -> ModerationCase:
        """I-24: "Moderation state changes are executed only by the owning context on command
        from Moderation, never by direct mutation." `case.resolve` raises
        `InvalidResolutionForSubjectError` if `action` is not valid for this case's own subject
        type -- `ModerationActionService.execute` is only ever reached with an already-validated
        pairing."""
        case = await self.get_case(case_id)
        resolved = case.resolve(
            action=action, note=note, moderator_user_id=moderator_user_id, now=now
        )
        saved = await self._cases.save(resolved)
        await self._outbox.append(
            ModerationActionTaken(
                event_id=uuid4(),
                occurred_at=now,
                actor=moderator_user_id,
                aggregate_type="ModerationCase",
                aggregate_id=saved.id,
                payload={
                    "moderationCaseId": str(saved.id),
                    "subjectType": saved.subject.subject_type.value,
                    "subjectId": str(saved.subject.subject_id),
                    "action": action.value,
                    "moderatorUserId": str(moderator_user_id),
                },
            )
        )
        await self._action_service.execute(saved)
        return saved
