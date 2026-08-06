"""Proves DB Architecture Sec 1.3's second sanctioned synchronous exception: a listing state
transition and its outbox event append commit in ONE transaction (DEC-09 generalised, never
dual-write). A forced failure between the two writes and the commit rolls both back together --
neither the aggregate's new state nor the outbox row survives, and a later poll sees the listing
still in its pre-transition state with no event ever risking delivery for a change that never
actually happened.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ListingType
from catalog.infrastructure.persistence.models import OutboxEventRow
from catalog.infrastructure.persistence.repository import SqlalchemyListingRepository
from contracts.events.catalog import ListingPublished
from shared_kernel import ListingId, UserId

NOW = datetime(2026, 7, 11, tzinfo=UTC)


class _SimulatedFailure(Exception):
    pass


def _new_draft(owner: UserId) -> Listing:
    return Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=owner,
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/x",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="Atomicity fixture",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="atomicity-fixture",
        now=NOW,
    )


async def test_forced_failure_rolls_back_both_the_transition_and_the_outbox_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = UserId(value=uuid4())
    listing = _new_draft(owner)

    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        await session.commit()

    with pytest.raises(_SimulatedFailure):
        async with session_factory() as session:
            repo = SqlalchemyListingRepository(session)
            loaded = await repo.get_by_id(listing.id)
            assert loaded is not None
            published = loaded.publish(
                record_id=uuid4(),
                actor_user_id=owner.value,
                expires_at=NOW + timedelta(days=30),
                now=NOW,
            )
            await repo.save(published)

            outbox = OutboxWriter(session, OutboxEventRow)
            await outbox.append(
                ListingPublished(
                    event_id=uuid4(),
                    occurred_at=NOW,
                    actor=owner.value,
                    aggregate_type="Listing",
                    aggregate_id=published.id.value,
                    payload={"listingId": str(published.id.value)},
                )
            )
            await session.flush()  # both writes are staged, neither committed yet

            raise _SimulatedFailure("simulated failure before commit")
            await session.commit()  # pragma: no cover -- unreachable, documents intent

    async with session_factory() as session:
        reloaded = await SqlalchemyListingRepository(session).get_by_id(listing.id)
        assert reloaded is not None
        assert reloaded.lifecycle_state.value == "DRAFT", "the transition must not have survived"
        assert reloaded.published_at is None

        outbox_rows = (await session.execute(select(OutboxEventRow))).scalars().all()
        assert outbox_rows == [], "the outbox row must not have survived either"


async def test_successful_commit_persists_both_together(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = UserId(value=uuid4())
    listing = _new_draft(owner)

    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyListingRepository(session)
        loaded = await repo.get_by_id(listing.id)
        assert loaded is not None
        published = loaded.publish(
            record_id=uuid4(),
            actor_user_id=owner.value,
            expires_at=NOW + timedelta(days=30),
            now=NOW,
        )
        await repo.save(published)
        outbox = OutboxWriter(session, OutboxEventRow)
        await outbox.append(
            ListingPublished(
                event_id=uuid4(),
                occurred_at=NOW,
                actor=owner.value,
                aggregate_type="Listing",
                aggregate_id=published.id.value,
                payload={"listingId": str(published.id.value)},
            )
        )
        await session.commit()

    async with session_factory() as session:
        reloaded = await SqlalchemyListingRepository(session).get_by_id(listing.id)
        assert reloaded is not None
        assert reloaded.lifecycle_state.value == "PUBLISHED"

        outbox_rows = (await session.execute(select(OutboxEventRow))).scalars().all()
        assert len(outbox_rows) == 1
        assert outbox_rows[0].event_type == "ListingPublished"
