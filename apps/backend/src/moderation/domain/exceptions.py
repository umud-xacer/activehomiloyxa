"""moderation -- typed domain exceptions, one per invariant violated (Playbook Sec 6). Mirrors
`profiles.domain.exceptions`'s style. `interfaces/errors.py` maps each of these to a
`contracts.errors.Problem` (closed `ErrorCode` vocabulary).
"""

from __future__ import annotations

from uuid import UUID


class ModerationDomainError(Exception):
    """Base for every typed exception raised by moderation's domain/ layer."""


class IllegalModerationCaseStateTransitionError(ModerationDomainError):
    """Attempted a transition method from a `CaseStatus` it does not accept."""

    def __init__(self, transition: str, current: str) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} a moderation case in status {current}")


class TerminalModerationCaseError(ModerationDomainError):
    """ "Retained permanently (guard trigger)" (Physical DB Design's own words for
    `moderation_case`) -- a `RESOLVED` case is terminal and immutable. Raised by every mutating
    `ModerationCase` method once `status` is `RESOLVED`."""

    def __init__(self, case_id: UUID, status: str) -> None:
        self.case_id = case_id
        self.status = status
        super().__init__(f"moderation case {case_id} is terminal ({status}) and cannot be modified")


class InvalidResolutionForSubjectError(ModerationDomainError):
    """A `ResolutionAction` that is not semantically valid for the case's own `SubjectType` --
    e.g. `SUSPEND_ACCOUNT` on a `LISTING`-subject case (`Listing` has no account to suspend). See
    `domain.value_objects.ACTIONS_BY_SUBJECT_TYPE`."""

    def __init__(self, action: str, subject_type: str) -> None:
        self.action = action
        self.subject_type = subject_type
        super().__init__(
            f"resolution action {action!r} is not valid for subject type {subject_type!r}"
        )
