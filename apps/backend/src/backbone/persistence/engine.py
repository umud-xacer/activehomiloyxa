"""Async SQLAlchemy engine + session factory (Playbook Sec 6: "I/O ... MUST be non-blocking";
DevSecOps Sec 7: "lock_timeout + statement_timeout set ... so a blocked DDL/DML fails fast
instead of queueing behind traffic"). Infra/runtime settings come from the environment
(Infra Sec 11), never hardcoded (AIR-06 is about business config, but the same fail-closed
discipline applies to required infra config -- Security Sec 14).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backbone.persistence.env import MissingInfraConfigError, required_env

MissingDatabaseConfigError = MissingInfraConfigError
"""Alias kept for readability at Postgres-specific call sites; the same exception type as every
other datastore's missing-config error (`backbone.persistence.env.MissingInfraConfigError`)."""


def database_url() -> str:
    """asyncpg DSN assembled from Infra Sec 11's environment-variable convention (POSTGRES_HOST
    et al., matching deployment/env/.env.*.example -- Task P-00)."""
    host = required_env("POSTGRES_HOST")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = required_env("POSTGRES_DB")
    user = required_env("POSTGRES_USER")
    password = required_env("POSTGRES_PASSWORD")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def make_engine(url: str | None = None) -> AsyncEngine:
    """One engine per process (connection-pooled); `lock_timeout`/`statement_timeout` are set
    per-connection via `connect_args` server settings so a blocked statement fails fast rather
    than queueing behind production traffic (DevSecOps Sec 7)."""
    return create_async_engine(
        url or database_url(),
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "lock_timeout": os.environ.get("DB_LOCK_TIMEOUT_MS", "5000"),
                "statement_timeout": os.environ.get("DB_STATEMENT_TIMEOUT_MS", "30000"),
            }
        },
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """`expire_on_commit=False`: use-case code commonly returns a result DTO built from the
    just-committed aggregate; SQLAlchemy's default post-commit attribute expiry would force an
    unwanted extra round-trip to re-read it (Physical DB Sec 13 N+1 guidance, same spirit)."""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One use case = one Session = one transaction (Physical DB Sec 13). Commits on clean
    exit, rolls back on any exception -- state and its outbox row(s) therefore always commit or
    roll back together, since both are written through the same `AsyncSession` before this
    single commit (DEC-09: never dual-write)."""
    async with session_factory() as session, session.begin():
        yield session
