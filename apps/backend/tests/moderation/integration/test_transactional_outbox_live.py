"""Proves DB Architecture Sec 1.3's sanctioned synchronous exception applies to moderation's own
`resolve_case` too: the `ModerationCase` resolution and its `ModerationActionTaken` outbox event
append commit in ONE transaction (DEC-09 generalised, never dual-write). A forced failure between
the writes and the commit rolls both back together -- neither the resolved case's new state nor
the outbox row survives. (The SEPARATE, eventually-consistent target-command dispatch --
`ModerationActionService.execute` -- is deliberately NOT part of this same transaction; see
`moderation_use_cases.py`'s own module docstring.)
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from contracts.events.moderation import ModerationActionTaken
from moderation.domain import ResolutionAction, Subject, SubjectType
from moderation.domain.moderation_case import ModerationCase
from moderation.infrastructure.persistence.models import OutboxEventRow
from moderation.infrastructure.persistence.repository import (
    SqlalchemyModerationCaseRepository,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


class _SimulatedFailure(Exception):
    pass


def _new_case() -> ModerationCase:
    return ModerationCase.open_from_report(
        case_id=uuid4(),
        subject=Subject(subject_type=SubjectType.LISTING, subject_id=uuid4()),
        reporter_user_id=uuid4(),
        reason="atomicity fixture",
        now=NOW,
    )


async def test_forced_failure_rolls_back_both_the_resolution_and_the_outbox_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    case = _new_case()
    async with session_factory() as session:
        await SqlalchemyModerationCaseRepository(session).add(case)
        await session.commit()

    moderator_id = uuid4()
    with pytest.raises(_SimulatedFailure):
        async with session_factory() as session:
            repo = SqlalchemyModerationCaseRepository(session)
            outbox = OutboxWriter(session, OutboxEventRow)
            fetched = await repo.get_by_id(case.id)
            assert fetched is not None
            resolved = fetched.resolve(
                action=ResolutionAction.DISMISS,
                note=None,
                moderator_user_id=moderator_id,
                now=NOW,
            )
            await repo.save(resolved)
            await outbox.append(
                ModerationActionTaken(
                    event_id=uuid4(),
                    occurred_at=NOW,
                    actor=moderator_id,
                    aggregate_type="ModerationCase",
                    aggregate_id=case.id,
                    payload={"moderationCaseId": str(case.id), "action": "DISMISS"},
                )
            )
            raise _SimulatedFailure()

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        reloaded = await repo.get_by_id(case.id)
        assert reloaded is not None
        assert reloaded.status.value == "OPEN"

        rows = (await session.execute(select(OutboxEventRow))).scalars().all()
        assert rows == []


async def test_committed_resolution_and_outbox_row_both_persist(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    case = _new_case()
    async with session_factory() as session:
        await SqlalchemyModerationCaseRepository(session).add(case)
        await session.commit()

    moderator_id = uuid4()
    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        outbox = OutboxWriter(session, OutboxEventRow)
        fetched = await repo.get_by_id(case.id)
        assert fetched is not None
        resolved = fetched.resolve(
            action=ResolutionAction.DISMISS,
            note=None,
            moderator_user_id=moderator_id,
            now=NOW,
        )
        await repo.save(resolved)
        await outbox.append(
            ModerationActionTaken(
                event_id=uuid4(),
                occurred_at=NOW,
                actor=moderator_id,
                aggregate_type="ModerationCase",
                aggregate_id=case.id,
                payload={"moderationCaseId": str(case.id), "action": "DISMISS"},
            )
        )
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        reloaded = await repo.get_by_id(case.id)
        assert reloaded is not None
        assert reloaded.status.value == "RESOLVED"

        rows = (await session.execute(select(OutboxEventRow))).scalars().all()
        assert len(rows) == 1
        assert rows[0].event_type == "ModerationActionTaken"
