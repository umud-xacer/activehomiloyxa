"""Fixtures for `messaging`'s real-Postgres/Redis integration tests (TEST-01: synthetic data
only). Skips gracefully when POSTGRES_HOST/REDIS_HOST aren't set (local `scripts/test.sh` without
`dev-up.sh` running); runs for real in CI. Mirrors `apps/backend/tests/identity/integration/
conftest.py`'s pattern exactly, plus `catalog`'s own schema (the listing-owner-projection
downstream test needs a real `ListingCreated` envelope, no catalog table required to construct
one synthetically)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.persistence import make_engine, make_session_factory, redis_url
from messaging.infrastructure.persistence import models  # noqa: F401  registers all ORM classes
from messaging.infrastructure.persistence.base import MessagingBase

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
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "messaging"'))
        await conn.run_sync(MessagingBase.metadata.create_all, checkfirst=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_messaging_tables(engine: AsyncEngine) -> AsyncIterator[None]:
    table_names = [t.name for t in MessagingBase.metadata.tables.values()]
    async with engine.begin() as conn:
        qualified = ", ".join(f'"messaging"."{name}"' for name in table_names)
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
async def _clean_redis_channels() -> AsyncIterator[None]:
    yield
    # pub/sub channels have no persistent keys to flush (Redis is a bus, not a store) -- nothing
    # to clean up here, unlike identity's session keys; kept as an explicit no-op fixture so a
    # future test that DOES leave keys behind (e.g. presence) has an obvious place to add cleanup.


@pytest.fixture
def redis_client() -> Redis:
    return Redis.from_url(redis_url())
