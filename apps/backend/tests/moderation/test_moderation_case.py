"""Domain-layer invariant tests for `moderation.domain.moderation_case.ModerationCase` (Task
P-12) -- terminal-immutability, the reviewer workflow (claim/resolve), and the fixed-verb /
subject-verb pairing guard (BR-MOD-02, `ACTIONS_BY_SUBJECT_TYPE`). Mirrors
`apps/backend/tests/profiles/test_verification_case.py`'s pattern exactly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from moderation.domain import (
    CaseStatus,
    IllegalModerationCaseStateTransitionError,
    InvalidResolutionForSubjectError,
    ModerationCase,
    OriginType,
    ResolutionAction,
    Subject,
    SubjectType,
    TerminalModerationCaseError,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _listing_case(**overrides: object) -> ModerationCase:
    defaults: dict[str, object] = {
        "case_id": uuid4(),
        "subject": Subject(subject_type=SubjectType.LISTING, subject_id=uuid4()),
        "reporter_user_id": uuid4(),
        "reason": "spam",
        "now": NOW,
    }
    defaults.update(overrides)
    return ModerationCase.open_from_report(**defaults)  # type: ignore[arg-type]


# --- factories (FR-MOD-001/002) -----------------------------------------------------------------


def test_open_from_report_produces_open_with_user_report_origin() -> None:
    case = _listing_case()
    assert case.status is CaseStatus.OPEN
    assert case.origin.origin_type is OriginType.USER_REPORT
    assert case.origin.report_reason == "spam"
    assert case.origin.rule_key is None
    assert case.reporter_user_id is not None
    assert case.resolution is None


def test_open_from_flag_produces_open_with_automated_flag_origin() -> None:
    case = ModerationCase.open_from_flag(
        case_id=uuid4(),
        subject=Subject(subject_type=SubjectType.LISTING, subject_id=uuid4()),
        rule_key="duplicate-detection",
        now=NOW,
    )
    assert case.status is CaseStatus.OPEN
    assert case.origin.origin_type is OriginType.AUTOMATED_FLAG
    assert case.origin.rule_key == "duplicate-detection"
    assert case.origin.report_reason is None
    assert case.reporter_user_id is None


# --- reviewer workflow (FR-MOD-003/004) -----------------------------------------------------------


def test_claim_from_open_advances_to_in_review() -> None:
    case = _listing_case().claim(now=NOW)
    assert case.status is CaseStatus.IN_REVIEW


def test_claim_twice_is_illegal() -> None:
    case = _listing_case().claim(now=NOW)
    with pytest.raises(IllegalModerationCaseStateTransitionError):
        case.claim(now=NOW)


def test_resolve_from_open_directly_is_legal() -> None:
    case = _listing_case().resolve(
        action=ResolutionAction.HIDE,
        note="policy violation",
        moderator_user_id=uuid4(),
        now=NOW,
    )
    assert case.status is CaseStatus.RESOLVED
    assert case.resolution is not None
    assert case.resolution.action is ResolutionAction.HIDE
    assert case.resolution.note == "policy violation"


def test_resolve_from_in_review_is_legal() -> None:
    case = _listing_case().claim(now=NOW)
    resolved = case.resolve(
        action=ResolutionAction.DISMISS, note=None, moderator_user_id=uuid4(), now=NOW
    )
    assert resolved.status is CaseStatus.RESOLVED


# --- BR-MOD-02: the fixed verb set, and its subject-scoped legality (ADR-0003) -------------------


def test_I24_resolve_with_action_not_valid_for_subject_type_raises() -> None:
    """The module's central guard: `SUSPEND_ACCOUNT` has no meaning on a LISTING-subject case
    (a `Listing` has no account to suspend) -- `ModerationCase.resolve` refuses it structurally,
    never leaving it to the caller/application layer to remember."""
    case = _listing_case()
    with pytest.raises(InvalidResolutionForSubjectError):
        case.resolve(
            action=ResolutionAction.SUSPEND_ACCOUNT,
            note=None,
            moderator_user_id=uuid4(),
            now=NOW,
        )


@pytest.mark.parametrize(
    ("subject_type", "action"),
    [
        (SubjectType.LISTING, ResolutionAction.HIDE),
        (SubjectType.LISTING, ResolutionAction.REJECT),
        (SubjectType.LISTING, ResolutionAction.SUSPEND),
        (SubjectType.LISTING, ResolutionAction.REMOVE),
        (SubjectType.LISTING, ResolutionAction.REQUEST_CORRECTION),
        (SubjectType.LISTING, ResolutionAction.DISMISS),
        (SubjectType.USER, ResolutionAction.SUSPEND_ACCOUNT),
        (SubjectType.USER, ResolutionAction.REQUEST_CORRECTION),
        (SubjectType.USER, ResolutionAction.DISMISS),
        (SubjectType.PROFILE, ResolutionAction.REVOKE_BADGE),
        (SubjectType.PROFILE, ResolutionAction.ARCHIVE_PROFILE),
        (SubjectType.PROFILE, ResolutionAction.REQUEST_CORRECTION),
        (SubjectType.PROFILE, ResolutionAction.DISMISS),
        (SubjectType.CONVERSATION, ResolutionAction.SUSPEND_ACCOUNT),
        (SubjectType.CONVERSATION, ResolutionAction.REQUEST_CORRECTION),
        (SubjectType.CONVERSATION, ResolutionAction.DISMISS),
    ],
)
def test_every_legal_subject_action_pairing_resolves(
    subject_type: SubjectType, action: ResolutionAction
) -> None:
    case = ModerationCase.open_from_flag(
        case_id=uuid4(),
        subject=Subject(subject_type=subject_type, subject_id=uuid4()),
        rule_key="r",
        now=NOW,
    )
    resolved = case.resolve(action=action, note=None, moderator_user_id=uuid4(), now=NOW)
    assert resolved.status is CaseStatus.RESOLVED
    assert resolved.resolution is not None
    assert resolved.resolution.action is action


@pytest.mark.parametrize(
    ("subject_type", "action"),
    [
        (SubjectType.LISTING, ResolutionAction.SUSPEND_ACCOUNT),
        (SubjectType.LISTING, ResolutionAction.REVOKE_BADGE),
        (SubjectType.LISTING, ResolutionAction.ARCHIVE_PROFILE),
        (SubjectType.USER, ResolutionAction.HIDE),
        (SubjectType.USER, ResolutionAction.REVOKE_BADGE),
        (SubjectType.PROFILE, ResolutionAction.HIDE),
        (SubjectType.PROFILE, ResolutionAction.SUSPEND_ACCOUNT),
        (SubjectType.CONVERSATION, ResolutionAction.HIDE),
        (SubjectType.CONVERSATION, ResolutionAction.REVOKE_BADGE),
    ],
)
def test_every_illegal_subject_action_pairing_raises(
    subject_type: SubjectType, action: ResolutionAction
) -> None:
    case = ModerationCase.open_from_flag(
        case_id=uuid4(),
        subject=Subject(subject_type=subject_type, subject_id=uuid4()),
        rule_key="r",
        now=NOW,
    )
    with pytest.raises(InvalidResolutionForSubjectError):
        case.resolve(action=action, note=None, moderator_user_id=uuid4(), now=NOW)


# --- terminal-immutability: RESOLVED is TERMINAL ------------------------------------------------


def test_terminal_case_cannot_be_claimed() -> None:
    case = _listing_case().resolve(
        action=ResolutionAction.DISMISS, note=None, moderator_user_id=uuid4(), now=NOW
    )
    with pytest.raises(TerminalModerationCaseError):
        case.claim(now=NOW)


def test_terminal_case_cannot_be_resolved_again() -> None:
    case = _listing_case().resolve(
        action=ResolutionAction.DISMISS, note=None, moderator_user_id=uuid4(), now=NOW
    )
    with pytest.raises(TerminalModerationCaseError):
        case.resolve(action=ResolutionAction.HIDE, note=None, moderator_user_id=uuid4(), now=NOW)


def test_terminal_guard_fires_before_the_subject_action_guard() -> None:
    """Terminal-immutability is checked FIRST in every mutating method (module docstring) -- even
    an action that would ALSO be illegal for the subject type must still surface as terminal, not
    as an invalid-pairing error, once the case is resolved."""
    case = _listing_case().resolve(
        action=ResolutionAction.DISMISS, note=None, moderator_user_id=uuid4(), now=NOW
    )
    with pytest.raises(TerminalModerationCaseError):
        case.resolve(
            action=ResolutionAction.SUSPEND_ACCOUNT,
            note=None,
            moderator_user_id=uuid4(),
            now=NOW,
        )
