"""The module's most important test (P-12 task prompt): proves `ModerationActionService.execute`
turns a resolved `ModerationCase`'s verb into EXACTLY ONE call on EXACTLY the right narrow command
port, with the right arguments, and NEVER more than one call across all three ports -- the
"interface-only-action" guarantee (`moderation/application/action_service.py`'s own docstring: "the
ONLY place a resolved ModerationCase's ResolutionAction turns into an actual cross-module
command... never a static import, never a direct write to another module's tables"). Complements
`test_boundary_import.py`'s static (import-linter) proof with a dynamic (behavioural) one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from moderation.application.action_service import ModerationActionService
from moderation.application.exceptions import UnresolvedModerationCaseError
from moderation.domain import ResolutionAction, Subject, SubjectType
from moderation.domain.moderation_case import ModerationCase

from .conftest import (
    FakeAccountSuspensionCommandPort,
    FakeListingModerationCommandPort,
    FakeProfileModerationCommandPort,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _resolved_case(subject_type: SubjectType, action: ResolutionAction) -> ModerationCase:
    moderator_id = uuid4()
    case = ModerationCase.open_from_flag(
        case_id=uuid4(),
        subject=Subject(subject_type=subject_type, subject_id=uuid4()),
        rule_key="r",
        now=NOW,
    )
    return case.resolve(action=action, note="reason-x", moderator_user_id=moderator_id, now=NOW)


@pytest.mark.parametrize(
    ("action", "listing_method"),
    [
        (ResolutionAction.HIDE, "hide_listing"),
        (ResolutionAction.REJECT, "reject_listing"),
        (ResolutionAction.SUSPEND, "suspend_listing"),
        (ResolutionAction.REMOVE, "remove_listing"),
    ],
)
@pytest.mark.asyncio
async def test_listing_verbs_call_exactly_one_listing_command_method(
    action_service: ModerationActionService,
    fake_listings: FakeListingModerationCommandPort,
    fake_accounts: FakeAccountSuspensionCommandPort,
    fake_profiles: FakeProfileModerationCommandPort,
    action: ResolutionAction,
    listing_method: str,
) -> None:
    case = _resolved_case(SubjectType.LISTING, action)
    await action_service.execute(case)

    assert len(fake_listings.calls) == 1
    method_name, listing_id, moderator_user_id, reason = fake_listings.calls[0]
    assert method_name == listing_method
    assert listing_id == case.subject.subject_id
    assert moderator_user_id == case.resolution.moderator_user_id  # type: ignore[union-attr]
    assert reason == "reason-x"
    assert fake_accounts.calls == []
    assert fake_profiles.revoke_calls == []
    assert fake_profiles.archive_calls == []


@pytest.mark.asyncio
async def test_suspend_account_verb_calls_exactly_the_account_port(
    action_service: ModerationActionService,
    fake_listings: FakeListingModerationCommandPort,
    fake_accounts: FakeAccountSuspensionCommandPort,
    fake_profiles: FakeProfileModerationCommandPort,
) -> None:
    case = _resolved_case(SubjectType.USER, ResolutionAction.SUSPEND_ACCOUNT)
    await action_service.execute(case)

    assert fake_accounts.calls == [(case.subject.subject_id, "reason-x")]
    assert fake_listings.calls == []
    assert fake_profiles.revoke_calls == []
    assert fake_profiles.archive_calls == []


@pytest.mark.asyncio
async def test_revoke_badge_verb_calls_exactly_the_profile_port(
    action_service: ModerationActionService,
    fake_listings: FakeListingModerationCommandPort,
    fake_accounts: FakeAccountSuspensionCommandPort,
    fake_profiles: FakeProfileModerationCommandPort,
) -> None:
    case = _resolved_case(SubjectType.PROFILE, ResolutionAction.REVOKE_BADGE)
    await action_service.execute(case)

    assert fake_profiles.revoke_calls == [case.subject.subject_id]
    assert fake_profiles.archive_calls == []
    assert fake_listings.calls == []
    assert fake_accounts.calls == []


@pytest.mark.asyncio
async def test_archive_profile_verb_calls_exactly_the_profile_port(
    action_service: ModerationActionService,
    fake_listings: FakeListingModerationCommandPort,
    fake_accounts: FakeAccountSuspensionCommandPort,
    fake_profiles: FakeProfileModerationCommandPort,
) -> None:
    case = _resolved_case(SubjectType.PROFILE, ResolutionAction.ARCHIVE_PROFILE)
    await action_service.execute(case)

    assert fake_profiles.archive_calls == [case.subject.subject_id]
    assert fake_profiles.revoke_calls == []
    assert fake_listings.calls == []
    assert fake_accounts.calls == []


@pytest.mark.parametrize("action", [ResolutionAction.REQUEST_CORRECTION, ResolutionAction.DISMISS])
@pytest.mark.asyncio
async def test_no_target_verbs_call_no_port_at_all(
    action_service: ModerationActionService,
    fake_listings: FakeListingModerationCommandPort,
    fake_accounts: FakeAccountSuspensionCommandPort,
    fake_profiles: FakeProfileModerationCommandPort,
    action: ResolutionAction,
) -> None:
    case = _resolved_case(SubjectType.USER, action)
    await action_service.execute(case)

    assert fake_listings.calls == []
    assert fake_accounts.calls == []
    assert fake_profiles.revoke_calls == []
    assert fake_profiles.archive_calls == []


@pytest.mark.asyncio
async def test_execute_requires_an_already_resolved_case(
    action_service: ModerationActionService,
) -> None:
    unresolved = ModerationCase.open_from_flag(
        case_id=uuid4(),
        subject=Subject(subject_type=SubjectType.LISTING, subject_id=uuid4()),
        rule_key="r",
        now=NOW,
    )
    with pytest.raises(UnresolvedModerationCaseError):
        await action_service.execute(unresolved)
