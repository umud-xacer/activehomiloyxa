"""Degradation proof: a slow async consumer never blocks the write path. `backbone.outbox.
OutboxWriter.append` (`apps/backend/src/backbone/outbox/writer.py`) only `session.add()`s a row
on the SAME transaction as the aggregate write -- it never calls a handler, never awaits I/O
beyond the one INSERT the surrounding transaction already does. `OutboxDispatcher.drain_once`
(`apps/backend/src/backbone/outbox/dispatcher.py`) is a wholly separate, later, independently-
scheduled call that is the ONLY thing that ever invokes a handler. This test proves the
decoupling is real, not just structurally plausible from reading the source: a real write
(`FavoriteUseCases.add_favorite`) commits near-instantly even though the handler eventually
attached to this same outbox row is deliberately slow (`asyncio.sleep`), and that slow work
provably has NOT happened by the time the write returns -- only a separate `drain_once()` call
triggers it, and it does eventually converge (SAD Sec 9/19's "brief lag, never lost").
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxDispatcher, OutboxWriter
from catalog.application.favorite_use_cases import FavoriteUseCases
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ListingType
from catalog.infrastructure.persistence.base import CatalogBase
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.infrastructure.persistence.repository import (
    SqlalchemyFavoriteRepository,
    SqlalchemyListingRepository,
)
from shared_kernel import EventEnvelope, ListingId, UserId
from tests.integration.conftest import ensure_clean_schema

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
_HANDLER_DELAY_SECONDS = 1.0


@pytest_asyncio.fixture(autouse=True)
async def _catalog_schema(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "catalog", CatalogBase)


async def test_a_deliberately_slow_consumer_does_not_slow_down_the_write_that_produced_its_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_id = UserId(value=uuid4())
    favoriter_id = UserId(value=uuid4())
    listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=owner_id,
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/x",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="A listing whose favorite event has a slow consumer",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="a-listing-whose-favorite-event-has-a-slow-consumer",
        now=NOW,
    ).publish(
        record_id=uuid4(),
        actor_user_id=owner_id.value,
        expires_at=NOW + timedelta(days=30),
        now=NOW,
    )

    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        await session.commit()

    handled_event_ids: list[object] = []

    async def slow_handler(envelope: EventEnvelope) -> None:
        await asyncio.sleep(_HANDLER_DELAY_SECONDS)
        handled_event_ids.append(envelope.event_id)

    write_started_at = time.monotonic()
    async with session_factory() as session:
        favorite_use_cases = FavoriteUseCases(
            favorites=SqlalchemyFavoriteRepository(session),
            listings=SqlalchemyListingRepository(session),
            outbox=OutboxWriter(session, CatalogOutboxEventRow),
        )
        await favorite_use_cases.add_favorite(user_id=favoriter_id, listing_id=listing.id, now=NOW)
        await session.commit()
    write_elapsed_seconds = time.monotonic() - write_started_at

    assert write_elapsed_seconds < _HANDLER_DELAY_SECONDS, (
        "the write must not have waited on the (as yet unattached, unrun) slow consumer -- it "
        f"took {write_elapsed_seconds:.3f}s against a {_HANDLER_DELAY_SECONDS}s handler delay"
    )
    assert handled_event_ids == [], (
        "the slow handler must not have run at all yet -- only drain_once() below may invoke it"
    )

    dispatcher = OutboxDispatcher(session_factory, CatalogOutboxEventRow, slow_handler)
    drain_started_at = time.monotonic()
    processed = await dispatcher.drain_once()
    drain_elapsed_seconds = time.monotonic() - drain_started_at

    assert processed == 1
    assert drain_elapsed_seconds >= _HANDLER_DELAY_SECONDS, (
        "drain_once must have genuinely awaited the slow handler, not skipped it"
    )
    assert len(handled_event_ids) == 1, "the slow consumer must eventually converge"
