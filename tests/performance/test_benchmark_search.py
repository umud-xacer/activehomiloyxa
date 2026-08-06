"""NFR-PERF-001 benchmark: search responses SHALL complete within 500ms p95 under expected v1
load. Drives the REAL app under a REAL `uvicorn` process (see `harness.py`'s own docstring for
why not `TestClient`) against whatever data is currently seeded (`python -m tests.performance.
seed_cli` -- run it first; this test does NOT seed for you, seeding 100k listings inside a single
pytest run would make the suite unusable for routine CI). Skips gracefully if the catalog schema
looks unseeded.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from backbone.persistence import make_engine
from catalog.infrastructure.persistence.models import ListingRow
from tests.performance import operations
from tests.performance.harness import OperationResult, UvicornServer, run_operation_wave

pytestmark = pytest.mark.integration

_REPORT_PATH = Path(__file__).parent / "baseline_report_search.json"
_REQUESTS_PER_OPERATION = int(os.environ.get("PERF_REQUESTS_PER_OPERATION", "100"))
_CONCURRENCY = int(os.environ.get("PERF_CONCURRENCY", "20"))


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def category_id() -> str:
    # Deliberately a fresh, module-scoped engine of its own -- `tests/integration/conftest.py`'s
    # own `engine` fixture is function-scoped (a fresh engine per test, closed at teardown), which
    # cannot be requested by a module-scoped fixture (pytest's own scope-mismatch rule); this
    # benchmark's data-reading fixtures need to outlive a single test function.
    engine = make_engine()
    async with engine.begin() as conn:
        result = await conn.execute(select(ListingRow.category_id).limit(1))
        row = result.first()
    await engine.dispose()
    if row is None:
        pytest.skip(
            "no listings seeded -- run `python -m tests.performance.seed_cli --scale=...` first"
        )
    return str(row[0])


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def server() -> AsyncIterator[UvicornServer]:
    srv = UvicornServer(port=8331)
    await srv.start()
    yield srv
    srv.stop()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def client(server: UvicornServer) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=30.0) as c:
        yield c


@pytest.mark.asyncio(loop_scope="module")
async def test_search_benchmark(
    server: UvicornServer, client: httpx.AsyncClient, category_id: str
) -> None:
    # `category_id`'s skip guard only proves a listing row exists -- it says nothing about
    # whether `configuration` has a published SearchConfiguration, which `GET /api/v1/search`
    # itself requires (503 DEPENDENCY_DEGRADED otherwise -- `python -m tests.performance.
    # seed_cli` publishes one as part of seeding). Without this check every request in the wave
    # below fails the same way and `run_operation_wave` swallows the real reason into a bare
    # error count.
    preflight = await client.get(f"{server.base_url}/api/v1/search", params={"q": "warmup"})
    if preflight.status_code == 503:
        pytest.skip(
            "no SearchConfiguration published -- run `python -m tests.performance.seed_cli` first"
        )

    results: list[OperationResult] = []

    results.append(
        await run_operation_wave(
            name="search_full_text",
            call=lambda c: operations.search_full_text(c, base_url=server.base_url),
            client=client,
            total_requests=_REQUESTS_PER_OPERATION,
            concurrency=_CONCURRENCY,
        )
    )
    results.append(
        await run_operation_wave(
            name="search_faceted",
            call=lambda c: operations.search_faceted(
                c, base_url=server.base_url, category_id=category_id
            ),
            client=client,
            total_requests=_REQUESTS_PER_OPERATION,
            concurrency=_CONCURRENCY,
        )
    )
    results.append(
        await run_operation_wave(
            name="search_geo",
            call=lambda c: operations.search_geo(c, base_url=server.base_url),
            client=client,
            total_requests=_REQUESTS_PER_OPERATION,
            concurrency=_CONCURRENCY,
        )
    )
    results.append(
        await run_operation_wave(
            name="search_cross_script",
            call=lambda c: operations.search_cross_script(c, base_url=server.base_url),
            client=client,
            total_requests=_REQUESTS_PER_OPERATION,
            concurrency=_CONCURRENCY,
        )
    )
    results.append(
        await run_operation_wave(
            name="search_suggest",
            call=lambda c: operations.search_suggest(c, base_url=server.base_url),
            client=client,
            total_requests=_REQUESTS_PER_OPERATION,
            concurrency=_CONCURRENCY,
        )
    )

    report = {
        "nfr": "NFR-PERF-001",
        "target_p95_ms": 500,
        "operations": [r.to_dict() for r in results],
    }
    _REPORT_PATH.write_text(json.dumps(report, indent=2))

    for result in results:
        print(f"{result.name}: {result.to_dict()}")
        assert result.errors < result.errors + len(result.latencies_ms), (
            f"{result.name}: every request errored"
        )
