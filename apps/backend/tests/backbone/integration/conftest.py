from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from backbone.persistence import make_engine

# NOTE: the `integration` marker is applied by path in the test-root `conftest.py`, not
# here. A `pytestmark` in a conftest marks nothing -- it applies only to tests declared in
# the same module, and a conftest declares none -- which is why `-m "not integration"`
# used to run these truncating suites instead of excluding them.

POSTGRES_AVAILABLE = bool(os.environ.get("POSTGRES_HOST"))


@pytest.fixture(autouse=True)
def _skip_without_postgres() -> None:
    """Every test under integration/ needs real PostgreSQL (TEST-01: synthetic data only,
    never a mock -- an outbox-atomicity claim proven against a mock proves nothing). Skips
    gracefully for local `scripts/test.sh` without docker running; CI's qg03-tests job (Task
    P-00) always has POSTGRES_HOST set."""
    if not POSTGRES_AVAILABLE:
        pytest.skip("POSTGRES_HOST not set -- no real Postgres to test against")


@pytest_asyncio.fixture
async def scratch_schema() -> AsyncIterator[str]:
    """A fresh, uniquely-named schema per test -- created before, dropped after, regardless of
    test outcome. Never a real module's schema name (TEST-01: synthetic data only)."""
    schema_name = f"scratch_{uuid.uuid4().hex[:12]}"
    engine: AsyncEngine = make_engine()
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    try:
        yield schema_name
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        await engine.dispose()
