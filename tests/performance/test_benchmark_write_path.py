"""Write-path benchmark: the aggregate+outbox commit latency for listing publish, measured at
the USE-CASE level (real `ListingUseCases`/`SqlalchemyListingRepository`/real Postgres), isolated
from HTTP/serialization overhead -- no SLO is named for this specifically in the SRS, but SAD §10
frames "commits state and its outbox event in one transaction" as the write path's own defining
property, worth measuring on its own. Needs seeded data (`python -m tests.performance.seed_cli`).
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from backbone.persistence import redis_url
from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.listing_use_cases import ListingUseCases
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.value_objects import ListingType
from catalog.infrastructure.configuration_adapter import (
    ConfigurationCategoryFormAdapter,
    ConfigurationPlatformSettingsAdapter,
)
from catalog.infrastructure.persistence.models import ListingRow
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.infrastructure.persistence.repository import (
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from identity.infrastructure.persistence.models import UserAccountRow
from shared_kernel import GeoLocation, Money, UserId
from tests.performance.seed import (
    NOW,
    _CategoryReaderBridge,
    _ConfigurationBridge,
    _NoCreditBalancePort,
    _NoMediaAssetReaderPort,
)

pytestmark = pytest.mark.integration

_REPORT_PATH = Path(__file__).parent / "baseline_report_write_path.json"
_ITERATIONS = 50


async def test_write_path_benchmark(
    engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with engine.begin() as conn:
        owner_row = (await conn.execute(select(UserAccountRow.id).limit(1))).first()
        category_row = (await conn.execute(select(ListingRow.category_id).limit(1))).first()
    if owner_row is None or category_row is None:
        pytest.skip("no seeded data -- run `python -m tests.performance.seed_cli` first")
    owner_id = UserId(value=owner_row[0])
    category_id = category_row[0]

    redis_client: Redis = Redis.from_url(redis_url())

    # `category_id` above is read off *some* pre-existing `catalog.listing` row -- in full-suite
    # order that table also holds other test suites' throwaway listings with random, never
    # registered category ids, so it isn't necessarily a category `configuration` actually
    # knows about. Resolve it through the same adapter `create_listing()` itself uses and skip
    # cleanly rather than let a genuinely-unseeded run fail deep inside the use case.
    category_reader = ConfigurationCategoryFormAdapter(
        _CategoryReaderBridge(session_factory, redis_client)
    )
    category_snapshot = await category_reader.get_category(category_id)
    if category_snapshot is None or category_snapshot.status != "ACTIVE":
        await redis_client.aclose()
        pytest.skip("no seeded data -- run `python -m tests.performance.seed_cli` first")

    latencies_ms: list[float] = []

    for _ in range(_ITERATIONS):
        async with session_factory() as session:
            listings_repo = SqlalchemyListingRepository(session)
            use_cases = ListingUseCases(
                listings=listings_repo,
                categories=ConfigurationCategoryFormAdapter(
                    _CategoryReaderBridge(session_factory, redis_client)
                ),
                settings=ConfigurationPlatformSettingsAdapter(
                    _ConfigurationBridge(session_factory, redis_client)
                ),
                media=_NoMediaAssetReaderPort(),
                outbox=OutboxWriter(session, CatalogOutboxEventRow),
                quota=QuotaEnforcementService(
                    subscriptions=SqlalchemySubscriptionSnapshotRepository(session)
                ),
                duplicates=DuplicateDetectionService(listings=listings_repo),
                credit_balance=_NoCreditBalancePort(),
            )
            started = time.monotonic()
            await use_cases.create_listing(
                owner_user_id=owner_id,
                owner_profile_id=None,
                listing_type=ListingType.ADVERTISEMENT,
                category_id=category_id,
                title=f"Write-path benchmark listing {uuid4()}",
                description="Write-path aggregate+outbox commit latency benchmark.",
                attributes={"rooms": "2"},
                price=Money(amount=Decimal("1500000"), currency="UZS"),
                location=GeoLocation(latitude=41.30, longitude=69.25),
                image_media_asset_ids=None,
                publish=False,
                now=NOW,
            )
            await session.commit()
            latencies_ms.append((time.monotonic() - started) * 1000)

    await redis_client.aclose()

    latencies_ms.sort()

    def _pct(p: float) -> float:
        return latencies_ms[min(len(latencies_ms) - 1, int(len(latencies_ms) * p / 100))]

    report = {
        "operation": "listing_create_draft_write_path",
        "count": len(latencies_ms),
        "p50_ms": round(_pct(50), 2),
        "p95_ms": round(_pct(95), 2),
        "p99_ms": round(_pct(99), 2),
    }
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"write_path: {report}")
