"""Shared Alembic `env.py` logic (Physical DB Sec 12/13). Migration files themselves live
per-module at `src/<module>/infrastructure/migrations/` (Sec 13 "Migration organization"), each
with its own `alembic.ini`/`versions/` and a thin `env.py` that only calls `run_migrations()`
here -- this is where the actual (identical, per-module) boilerplate lives once, not thirteen
times.

Async-capable (DevSecOps Sec 7); sets `lock_timeout`/`statement_timeout` so a blocked DDL fails
fast instead of queueing behind traffic; targets `version_table_schema=<module>` so each
module's Alembic version table lives inside that module's own schema (Physical DB Sec 1.1:
"Alembic version tables live per module branch inside the owning schema").

A module's own `env.py` is expected to be exactly:

    from backbone.migrations.env_support import run_migrations
    from catalog.infrastructure.models import Base  # the module's own declarative base

    run_migrations(module_name="catalog", target_metadata=Base.metadata)
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

from backbone.persistence.engine import database_url

if TYPE_CHECKING:
    from sqlalchemy import MetaData


def run_migrations(*, module_name: str, target_metadata: MetaData) -> None:
    """Call this, and only this, from a module's `env.py`. Dispatches to Alembic's offline
    (SQL-script generation) or online (real connection) mode exactly as Alembic's own
    generated `env.py` would, just parameterised by module."""
    config = context.config
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)

    if context.is_offline_mode():
        _run_migrations_offline(module_name, target_metadata)
    else:
        asyncio.run(_run_migrations_online(module_name, target_metadata))


def _run_migrations_offline(module_name: str, target_metadata: MetaData) -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        version_table_schema=module_name,
        include_schemas=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_migrations_online(module_name: str, target_metadata: MetaData) -> None:
    # DevSecOps Sec 7: "lock_timeout + statement_timeout set in the Alembic env so a blocked DDL
    # fails fast instead of queueing behind traffic." Set via connect_args (not a separate
    # `SET ...` statement executed before the migration): an earlier revision of this function
    # issued them as their own `connection.execute()` calls, which silently auto-began a
    # transaction that Alembic's own `context.begin_transaction()` then nested inside rather
    # than owned -- the whole thing (SET statements *and* the migration DDL) rolled back on
    # connection close instead of committing. connect_args applies the settings at the libpq
    # session level with no separate statement, so no autobegin happens before Alembic starts
    # its own transaction.
    connectable: AsyncEngine = async_engine_from_config(
        {"sqlalchemy.url": database_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={
            "server_settings": {
                "lock_timeout": "5000ms",
                "statement_timeout": "30000ms",
            }
        },
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_configure_and_run, module_name, target_metadata)
        await connection.commit()
    await connectable.dispose()


def _configure_and_run(connection: Connection, module_name: str, target_metadata: MetaData) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=module_name,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()
