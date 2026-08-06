"""Eventual-consistency proof for "catalog/messaging/ads metric events -> analytics MetricEvent +
ListingStatistics": a real `FavoriteUseCases.add_favorite` call produces a real `FavoriteAdded`
event on catalog's own outbox -> drained through analytics' REAL `handle_catalog_event` (the SAME
function `composition_root.make_catalog_outbox_fanout_handler`'s fifth route attaches in
production) -> a real, immutable `MetricEvent` fact row AND the derived `ListingStatistics.
favorites` counter, both in a real Postgres database (the genuinely partitioned/guard-triggered
schema, via the real Alembic migration -- see `tests/integration/conftest.py::
ensure_analytics_schema_via_migration`).

Also proves I-23's redelivery-is-a-no-op guarantee (idempotent_consume, keyed on the triggering
`event_id`) at the SAME two layers analytics/README.md's own test suite proves it at individually
(fact capture AND the derived projection) -- here proven again as a genuine cross-module
convergence, not a same-module unit test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from analytics.application.metric_use_cases import MetricUseCases
from analytics.infrastructure.event_projection import handle_catalog_event
from analytics.infrastructure.persistence.base import AnalyticsBase
from analytics.infrastructure.persistence.models import MetricEventRow
from analytics.infrastructure.persistence.repository import (
    SqlalchemyListingStatisticsProjectionRepository,
    SqlalchemyMetricEventRepository,
)
from backbone.outbox import OutboxWriter
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
from tests.integration.conftest import (
    ensure_analytics_schema_via_migration,
    ensure_clean_schema,
)

NOW = datetime.now(UTC)
"""Real current time, not a fixed past/future instant (unlike this suite's other tests):
`analytics.metric_event`/`audit_entry` are RANGE-partitioned by month, and the real Alembic
migration this file applies (`ensure_analytics_schema_via_migration`) only precreates partitions
for the CURRENT month forward from whenever it actually runs -- a fixed past date has no
partition to insert into (`CheckViolationError: no partition of relation "metric_event" found`)."""


@pytest.fixture(scope="session", autouse=True)
def _analytics_schema_migrated() -> None:
    ensure_analytics_schema_via_migration()


@pytest_asyncio.fixture(autouse=True)
async def _catalog_and_analytics_schemas(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "catalog", CatalogBase)
    await ensure_clean_schema(engine, "analytics", AnalyticsBase)


async def test_a_real_favorite_added_event_becomes_a_metric_fact_and_a_statistics_counter(
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
        title="A listing someone will favorite",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="a-listing-someone-will-favorite",
        now=NOW,
    ).publish(
        record_id=uuid4(),
        actor_user_id=owner_id.value,
        expires_at=NOW + timedelta(days=30),
        now=NOW,
    )

    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        favorite_use_cases = FavoriteUseCases(
            favorites=SqlalchemyFavoriteRepository(session),
            listings=SqlalchemyListingRepository(session),
            outbox=OutboxWriter(session, CatalogOutboxEventRow),
        )
        await favorite_use_cases.add_favorite(user_id=favoriter_id, listing_id=listing.id, now=NOW)
        await session.commit()

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(CatalogOutboxEventRow).where(
                        CatalogOutboxEventRow.event_type == "FavoriteAdded"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )

    def _metric_use_cases(session: AsyncSession) -> MetricUseCases:
        return MetricUseCases(
            metrics=SqlalchemyMetricEventRepository(session),
            listing_statistics=SqlalchemyListingStatisticsProjectionRepository(session),
        )

    async with session_factory() as session, session.begin():
        await handle_catalog_event(session, envelope, metric_use_cases=_metric_use_cases(session))

    async with session_factory() as session:
        metric_rows = (
            (
                await session.execute(
                    select(MetricEventRow).where(
                        MetricEventRow.source_event_id == envelope.event_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(metric_rows) == 1
        assert metric_rows[0].metric_key == "FAVORITE_ADDED"

        stats = await _metric_use_cases(session).get_listing_statistics(listing.id)
        assert stats is not None
        assert stats.favorites == 1

    # Redelivery of the SAME event_id must be a no-op at BOTH layers (I-23) -- proven here as a
    # genuine cross-module convergence, not a same-module unit test.
    async with session_factory() as session, session.begin():
        await handle_catalog_event(session, envelope, metric_use_cases=_metric_use_cases(session))

    async with session_factory() as session:
        metric_rows = (
            (
                await session.execute(
                    select(MetricEventRow).where(
                        MetricEventRow.source_event_id == envelope.event_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(metric_rows) == 1, "redelivery must not double-write the fact"

        stats = await _metric_use_cases(session).get_listing_statistics(listing.id)
        assert stats is not None
        assert stats.favorites == 1, "redelivery must not double-count the derived projection"
