"""Shared fixtures for backbone's unit + integration tests. Integration tests need real
PostgreSQL (TEST-01: synthetic data only, never against a shared/real environment) -- they skip
gracefully when POSTGRES_HOST isn't set (local `scripts/test.sh` without docker running) and run
for real in CI (qg03-tests' postgres service container, Task P-00)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.persistence import make_engine, make_session_factory

POSTGRES_AVAILABLE = bool(os.environ.get("POSTGRES_HOST"))

requires_postgres = pytest.mark.skipif(
    not POSTGRES_AVAILABLE, reason="POSTGRES_HOST not set -- no real Postgres to test against"
)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(engine)
