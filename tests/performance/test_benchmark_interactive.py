"""NFR-PERF-002 benchmark: interactive system responses SHALL complete within 300ms p95 under
expected v1 load. Needs seeded data (`python -m tests.performance.seed_cli`) -- run first."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from backbone.persistence import redis_url
from catalog.infrastructure.persistence.models import ListingRow
from identity.domain.session import Session
from identity.infrastructure.persistence.models import UserAccountRow
from identity.infrastructure.session_store import RedisSessionRepository
from messaging.infrastructure.persistence.models import ConversationRow
from shared_kernel import UserId
from tests.performance import operations
from tests.performance.harness import OperationResult, UvicornServer, run_operation_wave
from tests.performance.seed import NOW

pytestmark = pytest.mark.integration

_REPORT_PATH = Path(__file__).parent / "baseline_report_interactive.json"
_REQUESTS_PER_OPERATION = int(os.environ.get("PERF_REQUESTS_PER_OPERATION", "100"))
_CONCURRENCY = int(os.environ.get("PERF_CONCURRENCY", "20"))


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def sample_listing_id(engine: AsyncEngine) -> str:
    async with engine.begin() as conn:
        row = (await conn.execute(select(ListingRow.id).limit(1))).first()
    if row is None:
        pytest.skip("no listings seeded -- run `python -m tests.performance.seed_cli` first")
    return str(row[0])


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def sample_category_id(engine: AsyncEngine) -> str:
    async with engine.begin() as conn:
        row = (await conn.execute(select(ListingRow.category_id).limit(1))).first()
    assert row is not None
    return str(row[0])


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def sample_conversation_id(engine: AsyncEngine) -> str | None:
    async with engine.begin() as conn:
        row = (await conn.execute(select(ConversationRow.id).limit(1))).first()
    return str(row[0]) if row is not None else None


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def bearer_token(engine: AsyncEngine, session_factory: object) -> str:
    """A real session, issued the same way `identity`'s own real domain/repository classes issue
    one for a real login -- not a forged/decoded token."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory: async_sessionmaker[AsyncSession] = session_factory  # type: ignore[assignment]
    async with factory() as session:
        row = (await session.execute(select(UserAccountRow.id).limit(1))).first()
        if row is None:
            pytest.skip("no users seeded -- run `python -m tests.performance.seed_cli` first")
        account_id = UserId(value=row[0])

    from identity.infrastructure.security import SessionTokenGeneratorAdapter

    token_generator = SessionTokenGeneratorAdapter()
    redis_client: Redis = Redis.from_url(redis_url())
    raw_token = f"perf-bench-token-{uuid4()}"
    session_obj = Session.issue(
        session_id=uuid4(),
        account_id=account_id,
        token_hash=token_generator.hash_token(raw_token),
        ip_address="127.0.0.1",
        user_agent="perf-benchmark",
        now=NOW,
        expires_at=NOW.replace(year=NOW.year + 1),
    )
    await RedisSessionRepository(redis_client).save(session_obj)
    await redis_client.aclose()
    return raw_token


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def server() -> AsyncIterator[UvicornServer]:
    srv = UvicornServer(port=8332)
    await srv.start()
    yield srv
    srv.stop()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def client(server: UvicornServer) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=30.0) as c:
        yield c


@pytest.mark.asyncio(loop_scope="module")
async def test_interactive_benchmark(
    server: UvicornServer,
    client: httpx.AsyncClient,
    sample_listing_id: str,
    sample_category_id: str,
    sample_conversation_id: str | None,
    bearer_token: str,
) -> None:
    results: list[OperationResult] = []

    results.append(
        await run_operation_wave(
            name="listing_detail",
            call=lambda c: operations.interactive_listing_detail(
                c, base_url=server.base_url, listing_id=sample_listing_id
            ),
            client=client,
            total_requests=_REQUESTS_PER_OPERATION,
            concurrency=_CONCURRENCY,
        )
    )
    results.append(
        await run_operation_wave(
            name="authenticated_me",
            call=lambda c: operations.interactive_authenticated_me(
                c, base_url=server.base_url, bearer_token=bearer_token
            ),
            client=client,
            total_requests=_REQUESTS_PER_OPERATION,
            concurrency=_CONCURRENCY,
        )
    )
    if sample_conversation_id is not None:
        results.append(
            await run_operation_wave(
                name="conversation_history",
                call=lambda c: operations.interactive_conversation_history(
                    c,
                    base_url=server.base_url,
                    conversation_id=sample_conversation_id,
                    bearer_token=bearer_token,
                ),
                client=client,
                total_requests=_REQUESTS_PER_OPERATION,
                concurrency=_CONCURRENCY,
            )
        )
    results.append(
        await run_operation_wave(
            name="banner_serve",
            call=lambda c: operations.interactive_banner_serve(
                c, base_url=server.base_url, slot_key="perf-nonexistent-slot"
            ),
            client=client,
            total_requests=_REQUESTS_PER_OPERATION,
            concurrency=_CONCURRENCY,
        )
    )

    async def _create_and_publish(c: httpx.AsyncClient) -> None:
        listing_id = await operations.interactive_listing_create(
            c,
            base_url=server.base_url,
            bearer_token=bearer_token,
            category_id=sample_category_id,
            title=f"Benchmark listing {uuid4()}",
        )
        await operations.interactive_listing_publish(
            c,
            base_url=server.base_url,
            bearer_token=bearer_token,
            listing_id=listing_id,
        )

    results.append(
        await run_operation_wave(
            name="listing_create_and_publish",
            call=_create_and_publish,
            client=client,
            total_requests=max(10, _REQUESTS_PER_OPERATION // 5),
            concurrency=min(5, _CONCURRENCY),
            warmup_requests=1,
        )
    )

    report = {
        "nfr": "NFR-PERF-002",
        "target_p95_ms": 300,
        "operations": [r.to_dict() for r in results],
    }
    _REPORT_PATH.write_text(json.dumps(report, indent=2))

    for result in results:
        print(f"{result.name}: {result.to_dict()}")
