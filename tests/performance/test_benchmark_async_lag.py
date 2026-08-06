"""Async-lag measurement: outbox->search indexing lag. No hard SLO exists for this (SAD §19 names
the eventual-consistency window as an ACCEPTED trade-off, "handled in UX," not a defect to
eliminate) -- measured and reported, never asserted PASS/FAIL against an invented number. Proves
a real `ListingPublished` event, appended to catalog's real outbox, becomes visible in a real
OpenSearch document, and reports how long that took.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from opensearchpy import OpenSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ListingType
from catalog.infrastructure.persistence.models import ListingRow
from catalog.infrastructure.persistence.models import OutboxEventRow as CatalogOutboxEventRow
from catalog.infrastructure.persistence.repository import SqlalchemyListingRepository
from contracts.events.catalog import ListingPublished
from search.infrastructure.event_projection import make_search_event_handler
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from shared_kernel import EventEnvelope, GeoLocation, ListingId, Money, UserId
from tests.performance.seed import NOW

pytestmark = pytest.mark.integration

_REPORT_PATH = Path(__file__).parent / "baseline_report_async_lag.json"
_ITERATIONS = 20
_INDEX_NAME = "listing_search_content_perf_lag"


async def test_search_indexing_lag(
    engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with engine.begin() as conn:
        category_row = (await conn.execute(select(ListingRow.category_id).limit(1))).first()
    if category_row is None:
        pytest.skip("no seeded data -- run `python -m tests.performance.seed_cli` first")
    category_id = category_row[0]

    client = OpenSearch(hosts=[{"host": "localhost", "port": 9200}])
    index = OpenSearchIndexAdapter(client, index_name=_INDEX_NAME)
    await index.delete_index()
    await index.ensure_index()
    search_handler = make_search_event_handler(session_factory=session_factory, index=index)

    lags_ms: list[float] = []
    for _ in range(_ITERATIONS):
        owner_id = UserId(value=uuid4())
        listing = Listing.create(
            listing_id=ListingId(value=uuid4()),
            record_id=uuid4(),
            listing_type=ListingType.ADVERTISEMENT,
            owner_user_id=owner_id,
            owner_profile_id=None,
            category_id=category_id,
            category_path="/housing/apartments",
            form_definition_id=uuid4(),
            form_definition_version_id=uuid4(),
            title="Async-lag benchmark listing",
            description=None,
            attributes={},
            price=Money(amount=Decimal("1000000"), currency="UZS"),
            location=GeoLocation(latitude=41.30, longitude=69.25),
            slug=f"async-lag-benchmark-{uuid4()}",
            now=NOW,
        ).publish(record_id=uuid4(), actor_user_id=owner_id.value, expires_at=NOW, now=NOW)

        async with session_factory() as session:
            await SqlalchemyListingRepository(session).add(listing)
            outbox = OutboxWriter(session, CatalogOutboxEventRow)
            await outbox.append(
                ListingPublished(
                    event_id=uuid4(),
                    occurred_at=NOW,
                    actor=owner_id.value,
                    aggregate_type="Listing",
                    aggregate_id=listing.id.value,
                    payload={
                        "listingId": str(listing.id.value),
                        "ownerUserId": str(owner_id.value),
                        "categoryId": str(category_id),
                        "categoryPath": "/housing/apartments",
                        "listingType": "ADVERTISEMENT",
                        "title": listing.title,
                        "description": None,
                        "attributes": {},
                        "price": {"amount": "1000000", "currency": "UZS"},
                        "location": {"latitude": 41.30, "longitude": 69.25},
                        "slug": listing.slug,
                        "lifecycleState": "PUBLISHED",
                        "isFlagged": False,
                        "expiresAt": NOW.isoformat(),
                        "publishedAt": NOW.isoformat(),
                        "promotion": None,
                    },
                )
            )
            await session.commit()
            row = (
                await session.execute(
                    select(CatalogOutboxEventRow).where(
                        CatalogOutboxEventRow.aggregate_id == listing.id.value,
                        CatalogOutboxEventRow.event_type == "ListingPublished",
                    )
                )
            ).scalar_one()
            envelope = EventEnvelope(
                event_id=row.id,
                event_type=row.event_type,
                occurred_at=row.occurred_at,
                actor=row.actor,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                aggregate_version=row.aggregate_version,
                payload=row.payload,
            )

        started = time.monotonic()
        await search_handler(envelope)
        lags_ms.append((time.monotonic() - started) * 1000)

    await index.delete_index()
    lags_ms.sort()

    def _pct(p: float) -> float:
        return lags_ms[min(len(lags_ms) - 1, int(len(lags_ms) * p / 100))]

    report = {
        "measurement": "catalog_outbox_to_search_index_lag",
        "note": "SAD Sec 19: an accepted eventual-consistency window, not a hard SLO -- reported "
        "for visibility, never asserted PASS/FAIL against an invented target",
        "count": len(lags_ms),
        "p50_ms": round(_pct(50), 2),
        "p95_ms": round(_pct(95), 2),
        "p99_ms": round(_pct(99), 2),
    }
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"async_lag: {report}")
