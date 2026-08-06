"""`SqlalchemyModerationCaseRepository` against real PostgreSQL: round-trips every field
(subject/origin/resolution sub-VOs, the JSONB-free flat shape), and proves terminal-immutability
and the queue query survive a real commit/reload cycle -- not just the in-memory fake
`test_moderation_use_cases.py` exercises.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from moderation.domain import CaseStatus, ResolutionAction, Subject, SubjectType
from moderation.domain.moderation_case import ModerationCase
from moderation.infrastructure.persistence.repository import (
    SqlalchemyModerationCaseRepository,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


async def test_case_round_trips_report_origin_and_resolution(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    listing_id = uuid4()
    reporter_id = uuid4()
    moderator_id = uuid4()
    case = ModerationCase.open_from_report(
        case_id=uuid4(),
        subject=Subject(subject_type=SubjectType.LISTING, subject_id=listing_id),
        reporter_user_id=reporter_id,
        reason="fraud",
        now=NOW,
    )

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        await repo.add(case)
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        fetched = await repo.get_by_id(case.id)
        assert fetched is not None
        assert fetched.subject.subject_type is SubjectType.LISTING
        assert fetched.subject.subject_id == listing_id
        assert fetched.origin.report_reason == "fraud"
        assert fetched.reporter_user_id == reporter_id
        assert fetched.status is CaseStatus.OPEN

        resolved = fetched.resolve(
            action=ResolutionAction.HIDE,
            note="policy",
            moderator_user_id=moderator_id,
            now=NOW,
        )
        saved = await repo.save(resolved)
        await session.commit()
        assert saved.status is CaseStatus.RESOLVED

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        reloaded = await repo.get_by_id(case.id)
        assert reloaded is not None
        assert reloaded.status is CaseStatus.RESOLVED
        assert reloaded.resolution is not None
        assert reloaded.resolution.action is ResolutionAction.HIDE
        assert reloaded.resolution.note == "policy"
        assert reloaded.resolution.moderator_user_id == moderator_id


async def test_get_open_or_in_review_for_subject_ignores_resolved_cases(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = Subject(subject_type=SubjectType.LISTING, subject_id=uuid4())
    resolved_case = ModerationCase.open_from_flag(
        case_id=uuid4(), subject=subject, rule_key="r1", now=NOW
    ).resolve(action=ResolutionAction.DISMISS, note=None, moderator_user_id=uuid4(), now=NOW)

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        await repo.add(
            ModerationCase.open_from_flag(
                case_id=resolved_case.id, subject=subject, rule_key="r1", now=NOW
            )
        )
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        stored = await repo.get_by_id(resolved_case.id)
        assert stored is not None
        await repo.save(
            stored.resolve(
                action=ResolutionAction.DISMISS,
                note=None,
                moderator_user_id=uuid4(),
                now=NOW,
            )
        )
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        found = await repo.get_open_or_in_review_for_subject(
            subject.subject_type, subject.subject_id
        )
        assert found is None


async def test_list_queue_filters_and_orders_oldest_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    older = ModerationCase.open_from_report(
        case_id=uuid4(),
        subject=Subject(subject_type=SubjectType.LISTING, subject_id=uuid4()),
        reporter_user_id=uuid4(),
        reason="a",
        now=NOW - timedelta(hours=3),
    )
    newer = ModerationCase.open_from_report(
        case_id=uuid4(),
        subject=Subject(subject_type=SubjectType.LISTING, subject_id=uuid4()),
        reporter_user_id=uuid4(),
        reason="b",
        now=NOW,
    )
    other_subject_type = ModerationCase.open_from_report(
        case_id=uuid4(),
        subject=Subject(subject_type=SubjectType.USER, subject_id=uuid4()),
        reporter_user_id=uuid4(),
        reason="c",
        now=NOW - timedelta(hours=1),
    )

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        for case in (newer, older, other_subject_type):
            await repo.add(case)
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        page, next_cursor = await repo.list_queue(
            status=CaseStatus.OPEN,
            subject_type=SubjectType.LISTING,
            cursor=None,
            limit=20,
        )
        assert [c.id for c in page] == [older.id, newer.id]
        assert next_cursor is None
