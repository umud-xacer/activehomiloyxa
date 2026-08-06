"""Fixtures for `configuration`'s real-Postgres/Redis integration tests (TEST-01: synthetic data
only, never a mock -- outbox atomicity and immutability claims proven against a mock prove
nothing). Skips gracefully when POSTGRES_HOST/REDIS_HOST aren't set (local `scripts/test.sh`
without `dev-up.sh` running); runs for real in CI.

Unlike `apps/backend/tests/backbone/integration/conftest.py`'s `scratch_schema` (a fresh,
uniquely-named schema per test): `configuration.infrastructure.persistence.base.ConfigurationBase`
is bound to the fixed `"configuration"` schema at import time (Physical DB Sec 2.4
schema-per-module), so its ORM classes cannot be retargeted to a per-test schema name the way
`backbone`'s test-only demo models can. Isolation here is table-truncation between tests instead.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from backbone.persistence import (
    make_engine,
    make_session_factory,
    redis_url,
    session_scope,
)
from configuration.application.category_read import CategoryReadUseCases
from configuration.application.exceptions import GateFailedError
from configuration.application.use_cases import ConfigurationUseCases
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence import models  # noqa: F401  registers all ORM classes
from configuration.infrastructure.persistence.base import ConfigurationBase
from configuration.infrastructure.persistence.models import OutboxEvent
from configuration.infrastructure.persistence.repository import (
    SqlalchemyConfigHeadRepository,
)

# NOTE: the `integration` marker is applied by path in the test-root `conftest.py`, not
# here. A `pytestmark` in a conftest marks nothing -- it applies only to tests declared in
# the same module, and a conftest declares none -- which is why `-m "not integration"`
# used to run these truncating suites instead of excluding them.

POSTGRES_AVAILABLE = bool(os.environ.get("POSTGRES_HOST"))
REDIS_AVAILABLE = bool(os.environ.get("REDIS_HOST"))


@pytest.fixture(autouse=True)
def _skip_without_datastores() -> None:
    if not POSTGRES_AVAILABLE:
        pytest.skip("POSTGRES_HOST not set -- no real Postgres to test against")
    if not REDIS_AVAILABLE:
        pytest.skip("REDIS_HOST not set -- no real Redis to test against")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    async with eng.begin() as conn:
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "configuration"'))
        await conn.run_sync(ConfigurationBase.metadata.create_all, checkfirst=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_configuration_tables(engine: AsyncEngine) -> AsyncIterator[None]:
    # `.tables.values()`, not `.sorted_tables`: CASCADE handles FK ordering itself, and the
    # category<->search_configuration<->form_definition FK cycle makes topological sort
    # (`sorted_tables`) impossible anyway (SAWarning).
    table_names = [t.name for t in ConfigurationBase.metadata.tables.values()]
    async with engine.begin() as conn:
        qualified = ", ".join(f'"configuration"."{name}"' for name in table_names)
        await conn.execute(text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker:  # type: ignore[type-arg]
    return make_session_factory(engine)


@pytest_asyncio.fixture(autouse=True)
async def _clean_redis_snapshots() -> AsyncIterator[None]:
    client: Redis = Redis.from_url(redis_url())

    async def _flush() -> None:
        async for key in client.scan_iter("configuration:snapshot:*"):
            await client.delete(key)

    try:
        await _flush()
        yield
        await _flush()
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(redis_url())
    try:
        yield client
    finally:
        await client.aclose()


OpenUseCases = Callable[[], AbstractAsyncContextManager[ConfigurationUseCases]]
OpenCategoryReadUseCases = Callable[[], AbstractAsyncContextManager[CategoryReadUseCases]]
OpenSession = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@pytest.fixture
def open_use_cases(
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    redis_client: Redis,
) -> OpenUseCases:
    """One call = one transaction (Physical DB Sec 13), matching how
    `composition_root.provide_configuration_use_cases` opens a fresh session per HTTP request --
    so a controlled-track test's maker call and checker call commit as two genuinely separate
    transactions, the same as production, not a single test-only session shared across both.

    Mirrors `composition_root.provide_configuration_use_cases`'s transaction handling exactly
    (including the `GateFailedError` commit-then-reraise special case -- see that function's
    docstring) rather than delegating to the generic `session_scope`, so this fixture doesn't
    silently diverge from what production actually does."""

    @asynccontextmanager
    async def _open() -> AsyncIterator[ConfigurationUseCases]:
        session = session_factory()
        repo = SqlalchemyConfigHeadRepository(session)
        outbox = OutboxWriter(session, OutboxEvent)
        cache = RedisSnapshotCache(redis_client)
        try:
            yield ConfigurationUseCases(repo, cache, outbox)
        except GateFailedError:
            await session.commit()
            raise
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()
        finally:
            await session.close()

    return _open


@pytest.fixture
def open_category_read_use_cases(
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    redis_client: Redis,
) -> OpenCategoryReadUseCases:
    @asynccontextmanager
    async def _open() -> AsyncIterator[CategoryReadUseCases]:
        async with session_scope(session_factory) as session:
            repo = SqlalchemyConfigHeadRepository(session)
            cache = RedisSnapshotCache(redis_client)
            yield CategoryReadUseCases(repo, cache)

    return _open


@pytest.fixture
def open_session(
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
) -> OpenSession:
    @asynccontextmanager
    async def _open() -> AsyncIterator[AsyncSession]:
        async with session_scope(session_factory) as session:
            yield session

    return _open
