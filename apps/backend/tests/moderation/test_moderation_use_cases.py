"""`moderation.application.ModerationUseCases` (Task P-12) -- exercised against the in-memory
fakes in `conftest.py`. Covers report intake (open-vs-attach), automated flagging, the reviewer
queue (status/subject filters + FIFO ordering), claim, and `resolve_case`'s two-phase
commit -> react shape (the `ModerationCase` resolution + its `ModerationActionTaken` outbox event
commit FIRST, then the target command dispatches as a separate step).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from moderation.application.action_service import ModerationActionService
from moderation.application.exceptions import ModerationCaseNotFoundError
from moderation.application.moderation_use_cases import ModerationUseCases
from moderation.domain import CaseStatus, ResolutionAction, SubjectType

from .conftest import (
    FakeAccountSuspensionCommandPort,
    FakeListingModerationCommandPort,
    FakeModerationCaseRepository,
    FakeOutbox,
    FakeProfileModerationCommandPort,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _use_cases(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> ModerationUseCases:
    return ModerationUseCases(cases=fake_cases, action_service=action_service, outbox=fake_outbox)


# --- report intake (FR-MOD-001/FR-MSG-005) --------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_report_opens_a_new_case(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    listing_id = uuid4()
    case = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=listing_id,
        reporter_user_id=uuid4(),
        reason="fraud",
        now=NOW,
    )
    assert case.status is CaseStatus.OPEN
    assert case.subject.subject_id == listing_id
    assert len(fake_cases.cases) == 1


@pytest.mark.asyncio
async def test_second_report_against_same_open_subject_attaches_not_duplicates(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    listing_id = uuid4()
    first = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=listing_id,
        reporter_user_id=uuid4(),
        reason="fraud",
        now=NOW,
    )
    second = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=listing_id,
        reporter_user_id=uuid4(),
        reason="spam too",
        now=NOW,
    )
    assert second.id == first.id
    assert len(fake_cases.cases) == 1


@pytest.mark.asyncio
async def test_report_against_a_resolved_subject_opens_a_fresh_case(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    listing_id = uuid4()
    first = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=listing_id,
        reporter_user_id=uuid4(),
        reason="fraud",
        now=NOW,
    )
    await use_cases.resolve_case(
        first.id,
        action=ResolutionAction.DISMISS,
        note=None,
        moderator_user_id=uuid4(),
        now=NOW,
    )
    second = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=listing_id,
        reporter_user_id=uuid4(),
        reason="again",
        now=NOW,
    )
    assert second.id != first.id
    assert len(fake_cases.cases) == 2


# --- automated flagging (FR-MOD-002) --------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_flag_opens_a_new_case_from_automated_flag(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    listing_id = uuid4()
    case = await use_cases.auto_flag(
        subject_type=SubjectType.LISTING,
        subject_id=listing_id,
        rule_key="duplicate",
        now=NOW,
    )
    assert case.origin.rule_key == "duplicate"
    assert case.reporter_user_id is None


@pytest.mark.asyncio
async def test_auto_flag_against_already_open_subject_attaches(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    listing_id = uuid4()
    first = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=listing_id,
        reporter_user_id=uuid4(),
        reason="fraud",
        now=NOW,
    )
    second = await use_cases.auto_flag(
        subject_type=SubjectType.LISTING,
        subject_id=listing_id,
        rule_key="duplicate",
        now=NOW,
    )
    assert second.id == first.id
    assert second.origin.report_reason == "fraud"  # still the original USER_REPORT origin


# --- query (FR-MOD-005) ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_case_not_found_raises(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    with pytest.raises(ModerationCaseNotFoundError):
        await use_cases.get_case(uuid4())


@pytest.mark.asyncio
async def test_list_queue_filters_by_status_and_subject_type_and_orders_oldest_first(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    older_listing = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=uuid4(),
        reporter_user_id=uuid4(),
        reason="a",
        now=NOW - timedelta(hours=2),
    )
    newer_listing = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=uuid4(),
        reporter_user_id=uuid4(),
        reason="b",
        now=NOW,
    )
    user_case = await use_cases.submit_report(
        subject_type=SubjectType.USER,
        subject_id=uuid4(),
        reporter_user_id=uuid4(),
        reason="c",
        now=NOW,
    )
    await use_cases.resolve_case(
        user_case.id,
        action=ResolutionAction.DISMISS,
        note=None,
        moderator_user_id=uuid4(),
        now=NOW,
    )

    listing_page, _ = await use_cases.list_queue(
        status=None, subject_type=SubjectType.LISTING, cursor=None, limit=20
    )
    assert [c.id for c in listing_page] == [older_listing.id, newer_listing.id]

    open_page, _ = await use_cases.list_queue(
        status=CaseStatus.OPEN, subject_type=None, cursor=None, limit=20
    )
    assert user_case.id not in [c.id for c in open_page]

    resolved_page, _ = await use_cases.list_queue(
        status=CaseStatus.RESOLVED, subject_type=None, cursor=None, limit=20
    )
    assert [c.id for c in resolved_page] == [user_case.id]


# --- reviewer workflow (FR-MOD-003/004) -----------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_case_advances_to_in_review(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    case = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=uuid4(),
        reporter_user_id=uuid4(),
        reason="a",
        now=NOW,
    )
    claimed = await use_cases.claim_case(case.id, now=NOW)
    assert claimed.status is CaseStatus.IN_REVIEW


@pytest.mark.asyncio
async def test_resolve_case_persists_resolution_publishes_event_and_dispatches_action(
    fake_cases: FakeModerationCaseRepository,
    fake_listings: FakeListingModerationCommandPort,
    fake_accounts: FakeAccountSuspensionCommandPort,
    fake_profiles: FakeProfileModerationCommandPort,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    listing_id = uuid4()
    case = await use_cases.submit_report(
        subject_type=SubjectType.LISTING,
        subject_id=listing_id,
        reporter_user_id=uuid4(),
        reason="spam",
        now=NOW,
    )
    moderator_id = uuid4()

    resolved = await use_cases.resolve_case(
        case.id,
        action=ResolutionAction.HIDE,
        note="violates policy",
        moderator_user_id=moderator_id,
        now=NOW,
    )

    assert resolved.status is CaseStatus.RESOLVED
    assert fake_cases.cases[case.id].status is CaseStatus.RESOLVED

    assert len(fake_outbox.events) == 1
    published = fake_outbox.events[0]
    assert published.event_type == "ModerationActionTaken"
    assert published.payload["moderationCaseId"] == str(case.id)
    assert published.payload["action"] == "HIDE"

    assert fake_listings.calls == [("hide_listing", listing_id, moderator_id, "violates policy")]
    assert fake_accounts.calls == []
    assert fake_profiles.revoke_calls == []


@pytest.mark.asyncio
async def test_resolve_case_not_found_raises(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_cases, action_service, fake_outbox)
    with pytest.raises(ModerationCaseNotFoundError):
        await use_cases.resolve_case(
            uuid4(),
            action=ResolutionAction.DISMISS,
            note=None,
            moderator_user_id=uuid4(),
            now=NOW,
        )
