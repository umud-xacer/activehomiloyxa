"""System-wide outbox-redelivery idempotency proof. `OutboxDispatcher`'s own module docstring
(`apps/backend/src/backbone/outbox/dispatcher.py`) states its contract plainly: "at-least-once
delivery to `handler` ... a handler that is not itself idempotent is a defect in the handler, not
here." This test forces a genuine redelivery -- not a second in-process call to the same handler
function (already proven at the handler level by `tests/integration/
test_catalog_metrics_to_analytics.py`), but a SECOND real `OutboxDispatcher.drain_once()` pass
over the SAME row, after resetting `dispatch_status` back to `PENDING` exactly the way a crash
between "handler succeeded" and "row marked DISPATCHED" would leave it -- and proves the
downstream side effect (`backbone.idempotency.idempotent_consume`-backed) is not duplicated.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from analytics.application.metric_use_cases import MetricUseCases
from analytics.infrastructure.event_projection import handle_catalog_event
from analytics.infrastructure.persistence.base import AnalyticsBase
from analytics.infrastructure.persistence.models import MetricEventRow
from analytics.infrastructure.persistence.repository import (
    SqlalchemyListingStatisticsProjectionRepository,
    SqlalchemyMetricEventRepository,
)
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
from tests.integration.conftest import (
    ensure_analytics_schema_via_migration,
    ensure_clean_schema,
)

NOW = datetime.now(UTC)
"""Real current time -- `analytics.metric_event` is RANGE-partitioned by month, see
`tests/integration/test_catalog_metrics_to_analytics.py` for why this must not be a fixed date."""


@pytest.fixture(scope="session", autouse=True)
def _analytics_schema_migrated() -> None:
    ensure_analytics_schema_via_migration()


@pytest_asyncio.fixture(autouse=True)
async def _catalog_and_analytics_schemas(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "catalog", CatalogBase)
    await ensure_clean_schema(engine, "analytics", AnalyticsBase)


async def test_redelivering_the_same_outbox_row_does_not_double_count_the_metric(
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
        title="A listing whose favorite event gets redelivered",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="a-listing-whose-favorite-event-gets-redelivered",
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

    async def analytics_handler(envelope: EventEnvelope) -> None:
        async with session_factory() as session, session.begin():
            await handle_catalog_event(
                session,
                envelope,
                metric_use_cases=MetricUseCases(
                    metrics=SqlalchemyMetricEventRepository(session),
                    listing_statistics=SqlalchemyListingStatisticsProjectionRepository(session),
                ),
            )

    dispatcher = OutboxDispatcher(session_factory, CatalogOutboxEventRow, analytics_handler)

    processed_first_pass = await dispatcher.drain_once()
    assert processed_first_pass == 1

    async with session_factory() as session:
        await session.execute(
            update(CatalogOutboxEventRow)
            .where(CatalogOutboxEventRow.event_type == "FavoriteAdded")
            .values(dispatch_status="PENDING", dispatched_at=None)
        )
        await session.commit()

    processed_second_pass = await dispatcher.drain_once()
    assert processed_second_pass == 1, "the row must genuinely be redelivered, not skipped"

    async with session_factory() as session:
        metric_rows = (
            (
                await session.execute(
                    select(MetricEventRow).where(MetricEventRow.metric_key == "FAVORITE_ADDED")
                )
            )
            .scalars()
            .all()
        )
        assert len(metric_rows) == 1, "redelivery must not create a second MetricEvent fact"

        stats = await SqlalchemyListingStatisticsProjectionRepository(session).get_by_listing_id(
            listing.id
        )
        assert stats is not None
        assert stats.favorites == 1, "redelivery must not double-count the derived projection"
