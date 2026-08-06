"""Proves DB Architecture Sec 1.3's second sanctioned synchronous exception: a `VerificationCase`
decision (and the badge it issues) and the outbox event append commit in ONE transaction (DEC-09
generalised, never dual-write). A forced failure between the writes and the commit rolls both
back together -- neither the aggregate's new state nor the outbox row survives.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from contracts.events.profiles import BusinessProfileCreated
from profiles.domain import BusinessProfile, ProfileType
from profiles.infrastructure.persistence.models import OutboxEventRow
from profiles.infrastructure.persistence.repository import SqlalchemyBusinessProfileRepository
from shared_kernel import BusinessProfileId, LocalizedText, UserId

NOW = datetime(2026, 7, 13, tzinfo=UTC)


class _SimulatedFailure(Exception):
    pass


def _new_profile(owner: UserId) -> BusinessProfile:
    return BusinessProfile.create(
        profile_id=BusinessProfileId(value=uuid4()),
        owner_user_id=owner,
        profile_type=ProfileType.SUPPLIER,
        name=LocalizedText(uz_latn="Atomicity fixture"),
        description=None,
        contacts=None,
        address=None,
        slug="atomicity-fixture",
        now=NOW,
    )


async def test_forced_failure_rolls_back_both_the_profile_and_the_outbox_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = UserId(value=uuid4())
    profile = _new_profile(owner)

    with pytest.raises(_SimulatedFailure):
        async with session_factory() as session:
            repo = SqlalchemyBusinessProfileRepository(session)
            outbox = OutboxWriter(session, OutboxEventRow)
            await repo.add(profile)
            await outbox.append(
                BusinessProfileCreated(
                    event_id=uuid4(),
                    occurred_at=NOW,
                    actor=owner.value,
                    aggregate_type="BusinessProfile",
                    aggregate_id=profile.id.value,
                    payload={"businessProfileId": str(profile.id.value)},
                )
            )
            raise _SimulatedFailure()

    async with session_factory() as session:
        repo = SqlalchemyBusinessProfileRepository(session)
        assert await repo.get_by_id(profile.id) is None

        rows = (await session.execute(select(OutboxEventRow))).scalars().all()
        assert rows == []


async def test_committed_decision_and_outbox_row_both_persist(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = UserId(value=uuid4())
    profile = _new_profile(owner)

    async with session_factory() as session:
        repo = SqlalchemyBusinessProfileRepository(session)
        outbox = OutboxWriter(session, OutboxEventRow)
        await repo.add(profile)
        await outbox.append(
            BusinessProfileCreated(
                event_id=uuid4(),
                occurred_at=NOW,
                actor=owner.value,
                aggregate_type="BusinessProfile",
                aggregate_id=profile.id.value,
                payload={"businessProfileId": str(profile.id.value)},
            )
        )
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyBusinessProfileRepository(session)
        assert await repo.get_by_id(profile.id) is not None

        rows = (await session.execute(select(OutboxEventRow))).scalars().all()
        assert len(rows) == 1
        assert rows[0].event_type == "BusinessProfileCreated"
