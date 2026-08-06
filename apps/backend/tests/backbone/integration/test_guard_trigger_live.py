"""guard_trigger_ddl's generated SQL actually enforces immutability against real PostgreSQL
(Physical DB PD-07)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from backbone.migrations import guard_trigger_ddl
from backbone.persistence import make_engine


@pytest.fixture
async def append_only_table(scratch_schema: str) -> AsyncIterator[tuple[str, AsyncEngine]]:
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(f'CREATE TABLE "{scratch_schema}".append_only (id uuid PRIMARY KEY, note text)')
        )
        for stmt in guard_trigger_ddl(scratch_schema, "append_only"):
            await conn.execute(text(stmt))
    yield scratch_schema, engine
    await engine.dispose()


@pytest.fixture
async def partial_mutable_table(scratch_schema: str) -> AsyncIterator[tuple[str, AsyncEngine]]:
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f'CREATE TABLE "{scratch_schema}".partial_mutable '
                "(id uuid PRIMARY KEY, delivered_at timestamptz, other text)"
            )
        )
        for stmt in guard_trigger_ddl(
            scratch_schema, "partial_mutable", mutable_columns=("delivered_at",)
        ):
            await conn.execute(text(stmt))
    yield scratch_schema, engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_insert_is_allowed_on_append_only_table(
    append_only_table: tuple[str, AsyncEngine],
) -> None:
    schema, engine = append_only_table
    async with engine.begin() as conn:
        await conn.execute(
            text(f"INSERT INTO \"{schema}\".append_only VALUES (gen_random_uuid(), 'x')")
        )


@pytest.mark.asyncio
async def test_I14_update_is_rejected_on_append_only_table(
    append_only_table: tuple[str, AsyncEngine],
) -> None:
    schema, engine = append_only_table
    async with engine.begin() as conn:
        await conn.execute(
            text(f"INSERT INTO \"{schema}\".append_only VALUES (gen_random_uuid(), 'x')")
        )
    with pytest.raises(DBAPIError, match="immutability guard"):
        async with engine.begin() as conn:
            await conn.execute(text(f"UPDATE \"{schema}\".append_only SET note = 'y'"))


@pytest.mark.asyncio
async def test_I14_delete_is_rejected_on_append_only_table(
    append_only_table: tuple[str, AsyncEngine],
) -> None:
    schema, engine = append_only_table
    async with engine.begin() as conn:
        await conn.execute(
            text(f"INSERT INTO \"{schema}\".append_only VALUES (gen_random_uuid(), 'x')")
        )
    with pytest.raises(DBAPIError, match="immutability guard"):
        async with engine.begin() as conn:
            await conn.execute(text(f'DELETE FROM "{schema}".append_only'))


@pytest.mark.asyncio
async def test_allowed_column_update_succeeds_on_partial_mutable_table(
    partial_mutable_table: tuple[str, AsyncEngine],
) -> None:
    schema, engine = partial_mutable_table
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"INSERT INTO \"{schema}\".partial_mutable VALUES (gen_random_uuid(), NULL, 'orig')"
            )
        )
    async with engine.begin() as conn:
        await conn.execute(text(f'UPDATE "{schema}".partial_mutable SET delivered_at = now()'))


@pytest.mark.asyncio
async def test_I14_disallowed_column_update_rejected_on_partial_mutable_table(
    partial_mutable_table: tuple[str, AsyncEngine],
) -> None:
    schema, engine = partial_mutable_table
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"INSERT INTO \"{schema}\".partial_mutable VALUES (gen_random_uuid(), NULL, 'orig')"
            )
        )
    with pytest.raises(DBAPIError, match="immutability guard"):
        async with engine.begin() as conn:
            await conn.execute(text(f"UPDATE \"{schema}\".partial_mutable SET other = 'changed'"))
