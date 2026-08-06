"""Fixtures for `identity`'s real-Postgres/Redis integration tests (TEST-01: synthetic data
only). Skips gracefully when POSTGRES_HOST/REDIS_HOST aren't set (local `scripts/test.sh`
without `dev-up.sh` running); runs for real in CI. Mirrors
`apps/backend/tests/configuration/integration/conftest.py`'s pattern exactly."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.persistence import make_engine, make_session_factory, redis_url
from identity.infrastructure.persistence import models  # noqa: F401  registers all ORM classes
from identity.infrastructure.persistence.base import IdentityBase

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
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "identity"'))
        await conn.run_sync(IdentityBase.metadata.create_all, checkfirst=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_identity_tables(engine: AsyncEngine) -> AsyncIterator[None]:
    table_names = [t.name for t in IdentityBase.metadata.tables.values()]
    async with engine.begin() as conn:
        qualified = ", ".join(f'"identity"."{name}"' for name in table_names)
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


@pytest_asyncio.fixture(autouse=True)
async def _clean_redis_sessions() -> AsyncIterator[None]:
    client: Redis = Redis.from_url(redis_url())

    async def _flush() -> None:
        async for key in client.scan_iter("identity:session:*"):
            await client.delete(key)

    await _flush()
    yield
    await _flush()
    await client.aclose()


@pytest.fixture
def redis_client() -> Redis:
    return Redis.from_url(redis_url())
