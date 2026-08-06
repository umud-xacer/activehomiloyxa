"""moderation -- the `ModerationCase` aggregate (DDD Sec 5.11 `AR: ModerationCase [P]`).
Persistence-ignorant, mirrors `profiles.domain.verification_case.VerificationCase`'s style
exactly: frozen dataclass, every transition returns a new instance via `dataclasses.replace`,
guarded by a typed exception raised before the replace.

Terminal-immutability ("Retained permanently (guard trigger)", Physical DB Design's own words) is
enforced procedurally: every mutating method's FIRST check is `_guard_not_terminal`, before any
other validation -- there is no method on this class that can touch a case once `status` is
`RESOLVED`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from moderation.domain.exceptions import (
    IllegalModerationCaseStateTransitionError,
    InvalidResolutionForSubjectError,
    TerminalModerationCaseError,
)
from moderation.domain.value_objects import (
    ACTIONS_BY_SUBJECT_TYPE,
    TERMINAL_CASE_STATUSES,
    CaseStatus,
    Origin,
    Resolution,
    ResolutionAction,
    Subject,
)


@dataclass(frozen=True)
class ModerationCase:
    id: UUID
    subject: Subject
    origin: Origin
    reporter_user_id: UUID | None
    """Set only for `Origin.origin_type == USER_REPORT`; `None` for `AUTOMATED_FLAG` (Physical DB
    `reporter_user_id` is nullable, xref identity, no FK)."""
    status: CaseStatus
    resolution: Resolution | None
    created_at: datetime
    updated_at: datetime
    lock_version: int = 0

    # --- factories (FR-MOD-001/002) ---------------------------------------------------------------

    @staticmethod
    def open_from_report(
        *,
        case_id: UUID,
        subject: Subject,
        reporter_user_id: UUID,
        reason: str,
        now: datetime,
    ) -> ModerationCase:
        """FR-MOD-001/FR-MSG-005: "any user report a listing/conversation/account" -> "a report
        enters the moderation queue." Always produces `OPEN`."""
        return ModerationCase(
            id=case_id,
            subject=subject,
            origin=Origin.from_report(reason),
            reporter_user_id=reporter_user_id,
            status=CaseStatus.OPEN,
            resolution=None,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def open_from_flag(
        *, case_id: UUID, subject: Subject, rule_key: str, now: datetime
    ) -> ModerationCase:
        """FR-MOD-002: "automated validation rules... flag content at or after publication."
        `rule_key` is an opaque identifier carried by the triggering event (e.g. catalog's own
        `ListingFlagged.payload["reason"]`) -- moderation never evaluates the rule itself (see
        `moderation/README.md` "The FlaggingService is reactive-only")."""
        return ModerationCase(
            id=case_id,
            subject=subject,
            origin=Origin.from_flag(rule_key),
            reporter_user_id=None,
            status=CaseStatus.OPEN,
            resolution=None,
            created_at=now,
            updated_at=now,
        )

    # --- terminal-immutability guard -------------------------------------------------------------

    def _guard_not_terminal(self) -> None:
        if self.status in TERMINAL_CASE_STATUSES:
            raise TerminalModerationCaseError(self.id, self.status.value)

    # --- reviewer workflow (FR-MOD-003/004) --------------------------------------------------------

    def claim(self, *, now: datetime) -> ModerationCase:
        """A moderator claims the case from the queue. Legal from `OPEN` only. Physical DB's own
        `moderation_case` table has no separate "claimed by" column (only `moderator_user_id`,
        tied to the eventual `resolution`) -- claiming only advances `status`, the claimant is
        recorded once the case is actually resolved."""
        self._guard_not_terminal()
        if self.status is not CaseStatus.OPEN:
            raise IllegalModerationCaseStateTransitionError("claim", self.status.value)
        return replace(self, status=CaseStatus.IN_REVIEW, updated_at=now)

    def resolve(
        self,
        *,
        action: ResolutionAction,
        note: str | None,
        moderator_user_id: UUID,
        now: datetime,
    ) -> ModerationCase:
        """FR-MOD-003/004: "each action changes content state and is auditable." Legal from
        `OPEN` or `IN_REVIEW` (a moderator may resolve without a separate claim step, the same
        "claim is not a precondition of deciding" reasoning `profiles.domain.verification_case.
        VerificationCase.decide` documents for its own `mark_in_review`). Raises
        `InvalidResolutionForSubjectError` if `action` is not valid for this case's own
        `subject.subject_type` (`domain.value_objects.ACTIONS_BY_SUBJECT_TYPE`) -- e.g.
        `SUSPEND_ACCOUNT` on a `LISTING`-subject case."""
        self._guard_not_terminal()
        if self.status not in (CaseStatus.OPEN, CaseStatus.IN_REVIEW):
            raise IllegalModerationCaseStateTransitionError("resolve", self.status.value)
        if action not in ACTIONS_BY_SUBJECT_TYPE[self.subject.subject_type]:
            raise InvalidResolutionForSubjectError(action.value, self.subject.subject_type.value)
        resolution = Resolution(
            action=action,
            note=note,
            moderator_user_id=moderator_user_id,
            resolved_at=now,
        )
        return replace(self, status=CaseStatus.RESOLVED, resolution=resolution, updated_at=now)
