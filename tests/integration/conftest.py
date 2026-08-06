"""Shared fixtures for the cross-module eventual-consistency suite (P-20). Unlike a single
module's own `integration/conftest.py` (which creates and truncates ONE schema, since every test
in that directory needs only its own module's tables), a cross-module test needs a DIFFERENT
combination of schemas per pair of modules under test -- so this conftest provides only the bare
`engine`/`session_factory` against real PostgreSQL/Redis, and each test file creates (and, via
`ensure_clean_schema`, truncates) exactly the schemas its own scenario spans, mirroring
`apps/backend/tests/moderation/integration/test_account_suspension_compensation_live.py`'s own
already-established multi-schema pattern.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from backbone.persistence import make_engine, make_session_factory

pytestmark = pytest.mark.integration

POSTGRES_AVAILABLE = bool(os.environ.get("POSTGRES_HOST"))
REDIS_AVAILABLE = bool(os.environ.get("REDIS_HOST"))
OPENSEARCH_AVAILABLE = bool(os.environ.get("OPENSEARCH_HOST"))


@pytest.fixture(autouse=True)
def _skip_without_postgres() -> None:
    if not POSTGRES_AVAILABLE:
        pytest.skip(
            "POSTGRES_HOST not set -- no real Postgres to test the assembled system against"
        )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(engine)


async def ensure_clean_schema(
    engine: AsyncEngine, schema: str, base: type[DeclarativeBase]
) -> None:
    """Creates `schema`'s tables (from `base.metadata`) if missing, then truncates every one of
    them -- the same create-then-truncate sequence every module's own `integration/conftest.py`
    already runs for its single schema, generalised so a cross-module test can call it once per
    module its scenario touches."""
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        await conn.run_sync(base.metadata.create_all, checkfirst=True)
        table_names = [t.name for t in base.metadata.tables.values()]
        if table_names:
            qualified = ", ".join(f'"{schema}"."{name}"' for name in table_names)
            await conn.execute(text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"))


_ANALYTICS_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "apps/backend/src/analytics/infrastructure/migrations"
)


async def _precreate_analytics_schema() -> None:
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "analytics"'))
    await engine.dispose()


def ensure_analytics_schema_via_migration() -> None:
    """`ensure_clean_schema` (create-from-ORM-metadata) can't be used for `analytics` the first
    time: `audit_entry`/`metric_event` are hand-DDL'd RANGE-partitioned tables with an
    immutability guard trigger, neither of which SQLAlchemy's declarative metadata can produce
    (mirrors `apps/backend/tests/analytics/integration/conftest.py`'s own already-established
    pattern). Applies the REAL Alembic migration instead -- idempotent (`command.upgrade(...,
    "head")` no-ops once already at head), so it's safe to call from every test that touches
    analytics' schema. Sync and deliberately NOT a `pytest_asyncio.fixture`: `command.upgrade`
    runs its own internal `asyncio.run(...)`, which cannot nest inside a pytest-asyncio-managed
    event loop. Once this has run, a test's own per-test cleanup can go back to the normal
    `ensure_clean_schema(engine, "analytics", AnalyticsBase)` (its `create_all(checkfirst=True)`
    is a no-op since the tables already exist; only the `TRUNCATE` actually does anything)."""
    if not POSTGRES_AVAILABLE:
        return
    asyncio.run(_precreate_analytics_schema())
    cfg = Config(str(_ANALYTICS_MIGRATIONS_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ANALYTICS_MIGRATIONS_DIR))
    command.upgrade(cfg, "head")


async def poll_until[T](
    predicate: Callable[[], Awaitable[T | None]],
    *,
    timeout_seconds: float = 5.0,
    interval_seconds: float = 0.1,
) -> T:
    """The bounded, explicit async-consistency wait every eventual-consistency assertion in this
    suite uses (SAD Sec 9/19: "brief windows where read models lag" -- tolerated, never assumed
    away). `predicate` returns the awaited value once it becomes truthy/non-`None`; a timeout
    raises `AssertionError` naming what never converged, rather than hanging the suite."""
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    last: T | None = None
    while asyncio.get_event_loop().time() < deadline:
        last = await predicate()
        if last:
            return last
        await asyncio.sleep(interval_seconds)
    raise AssertionError(
        f"condition did not converge within {timeout_seconds}s (SAD Sec 9's eventual-consistency "
        f"window is meant to be brief, not unbounded) -- last observed value: {last!r}"
    )
