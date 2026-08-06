"""Fixtures for `analytics`'s real-Postgres integration tests (TEST-01: synthetic data only).
Skips gracefully when POSTGRES_HOST isn't set (local `scripts/test.sh` without `dev-up.sh`
running); runs for real in CI.

DELIBERATE DEVIATION from every other module's integration `conftest.py` (`ads`/`notifications`/
etc., which use `<Module>Base.metadata.create_all` for fixture setup, never the real migration):
`audit_entry`/`metric_event` are PARTITIONED tables with an immutability GUARD TRIGGER, neither
of which `metadata.create_all` can produce (SQLAlchemy has no `PARTITION BY` concept, and a
guard trigger is pure hand-written DDL, invisible to ORM metadata) -- and this task's own
validation checklist explicitly requires proving both at the database level. So this conftest
runs the REAL Alembic migration (`command.upgrade`, mirroring `apps/backend/tests/backbone/
integration/test_migrations_live.py`'s own invocation pattern) once per test session instead,
against analytics' own already-scaffolded `alembic.ini` -- idempotent (alembic no-ops once
already at head), and gives every test in this suite the real, production-shaped schema.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from analytics.infrastructure.persistence import models  # noqa: F401  registers all ORM classes
from analytics.infrastructure.persistence.base import AnalyticsBase
from backbone.persistence import make_engine, make_session_factory

# NOTE: the `integration` marker is applied by path in the test-root `conftest.py`, not
# here. A `pytestmark` in a conftest marks nothing -- it applies only to tests declared in
# the same module, and a conftest declares none -- which is why `-m "not integration"`
# used to run these truncating suites instead of excluding them.

POSTGRES_AVAILABLE = bool(os.environ.get("POSTGRES_HOST"))

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[5] / "apps/backend/src/analytics/infrastructure/migrations"
)


@pytest.fixture(autouse=True)
def _skip_without_datastores() -> None:
    if not POSTGRES_AVAILABLE:
        pytest.skip("POSTGRES_HOST not set -- no real Postgres to test against")


async def _precreate_schema() -> None:
    """Alembic's own `version_table_schema="analytics"` (Physical DB Sec 1.1: version tables
    live inside the owning schema) means alembic needs the schema to exist BEFORE it creates its
    bookkeeping table -- before this migration's own `upgrade()` (which also issues `CREATE
    SCHEMA IF NOT EXISTS`) ever runs. In real deployment this is deployment tooling's job
    (`backbone.persistence.schema_and_role_ddl`'s own per-module schema+role provisioning,
    Physical DB Sec 13); here, this test fixture does the equivalent bootstrap step."""
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "analytics"'))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _apply_real_migration() -> None:
    """Sync, session-scoped, and deliberately NOT a `pytest_asyncio.fixture` -- `command.upgrade`
    runs its own internal `asyncio.run(...)` (the standard Alembic async recipe), which cannot
    nest inside a pytest-asyncio-managed event loop."""
    if not POSTGRES_AVAILABLE:
        return
    asyncio.run(_precreate_schema())
    cfg = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_analytics_tables(engine: AsyncEngine) -> AsyncIterator[None]:
    table_names = [t.name for t in AnalyticsBase.metadata.tables.values()]
    async with engine.begin() as conn:
        qualified = ", ".join(f'"analytics"."{name}"' for name in table_names)
        # TRUNCATE on a partitioned parent cascades to all its partitions (Postgres, no separate
        # per-partition TRUNCATE needed).
        await conn.execute(text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(engine)


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
        await session.commit()
