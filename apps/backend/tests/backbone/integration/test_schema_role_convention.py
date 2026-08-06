"""The per-module schema/role convention (Physical DB PD-06: "One PostgreSQL role per module,
granted USAGE + DML only on its own schema") against real PostgreSQL: a scratch schema+role is
created, its privileges verified, then dropped -- confirming no cross-schema grant leaks."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from backbone.persistence import drop_schema_and_role_ddl, make_engine, schema_and_role_ddl


@pytest.fixture
def scratch_module_name() -> str:
    # a valid lowercase identifier, never one of the 13 real module names.
    return f"scratchmod{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def provisioned_module(
    scratch_module_name: str,
) -> AsyncIterator[tuple[str, AsyncEngine]]:
    engine = make_engine()
    statements = schema_and_role_ddl(scratch_module_name, role_password_env_placeholder=":pw")
    async with engine.begin() as conn:
        for stmt in statements:
            if ":pw" in stmt:
                await conn.execute(text(stmt), {"pw": "scratch_test_password_only"})
            else:
                await conn.execute(text(stmt))
    try:
        yield scratch_module_name, engine
    finally:
        async with engine.begin() as conn:
            for stmt in drop_schema_and_role_ddl(scratch_module_name):
                await conn.execute(text(stmt))
        await engine.dispose()


@pytest.mark.asyncio
async def test_I15_schema_and_role_are_created(
    provisioned_module: tuple[str, AsyncEngine],
) -> None:
    module_name, engine = provisioned_module
    async with engine.begin() as conn:
        schema_exists = await conn.scalar(
            text("SELECT 1 FROM pg_namespace WHERE nspname = :n"), {"n": module_name}
        )
        role_exists = await conn.scalar(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": f"ah_{module_name}"}
        )
    assert schema_exists == 1
    assert role_exists == 1


@pytest.mark.asyncio
async def test_I15_role_can_write_its_own_schema(
    provisioned_module: tuple[str, AsyncEngine],
) -> None:
    module_name, engine = provisioned_module
    role = f"ah_{module_name}"
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE TABLE "{module_name}".probe (id int PRIMARY KEY)'))
        can_insert = await conn.scalar(
            text("SELECT has_table_privilege(:role, :tbl, 'INSERT')"),
            {"role": role, "tbl": f"{module_name}.probe"},
        )
    assert can_insert is True


@pytest.mark.asyncio
async def test_I15_role_has_no_grants_on_a_different_schema(
    provisioned_module: tuple[str, AsyncEngine],
) -> None:
    """# enforces PD-06 / DEC-22: cross-module isolation is enforced by the database itself.

    Deliberately *not* checked against `public`: PostgreSQL grants every role USAGE on `public`
    by default (a global, database-wide default unrelated to this provisioning logic), so it
    would not actually exercise PD-06 -- it would just prove Postgres's own out-of-the-box
    behaviour. A second provisioned module (which this DDL explicitly `REVOKE ALL ... FROM
    PUBLIC`s, same as the first) is the real, faithful check."""
    module_name, engine = provisioned_module
    role = f"ah_{module_name}"
    other_module = f"scratchother{uuid.uuid4().hex[:8]}"

    statements = schema_and_role_ddl(other_module, role_password_env_placeholder=":pw")
    async with engine.begin() as conn:
        for stmt in statements:
            if ":pw" in stmt:
                await conn.execute(text(stmt), {"pw": "scratch_test_password_only"})
            else:
                await conn.execute(text(stmt))
    try:
        async with engine.begin() as conn:
            can_use_other = await conn.scalar(
                text("SELECT has_schema_privilege(:role, :schema, 'USAGE')"),
                {"role": role, "schema": other_module},
            )
        assert can_use_other is False
    finally:
        async with engine.begin() as conn:
            for stmt in drop_schema_and_role_ddl(other_module):
                await conn.execute(text(stmt))


@pytest.mark.asyncio
async def test_I15_public_has_no_access_to_the_module_schema(
    provisioned_module: tuple[str, AsyncEngine],
) -> None:
    module_name, engine = provisioned_module
    async with engine.begin() as conn:
        public_can_use = await conn.scalar(
            text("SELECT has_schema_privilege('public', :schema, 'USAGE')"),
            {"schema": module_name},
        )
    assert public_can_use is False


@pytest.mark.asyncio
async def test_teardown_leaves_no_schema_or_role_behind(scratch_module_name: str) -> None:
    engine = make_engine()
    statements = schema_and_role_ddl(scratch_module_name, role_password_env_placeholder=":pw")
    async with engine.begin() as conn:
        for stmt in statements:
            if ":pw" in stmt:
                await conn.execute(text(stmt), {"pw": "scratch_test_password_only"})
            else:
                await conn.execute(text(stmt))

    async with engine.begin() as conn:
        for stmt in drop_schema_and_role_ddl(scratch_module_name):
            await conn.execute(text(stmt))

    async with engine.begin() as conn:
        schema_exists = await conn.scalar(
            text("SELECT 1 FROM pg_namespace WHERE nspname = :n"), {"n": scratch_module_name}
        )
        role_exists = await conn.scalar(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"),
            {"r": f"ah_{scratch_module_name}"},
        )
    await engine.dispose()

    assert schema_exists is None
    assert role_exists is None
