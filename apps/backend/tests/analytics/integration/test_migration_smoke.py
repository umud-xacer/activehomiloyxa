"""Smoke test: the real migration applies cleanly and produces the expected physical shape
(partitioned tables + guard triggers) -- run first, in isolation, while developing the rest of
this suite."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_migration_created_partitioned_tables_with_guard_triggers(
    db_session: AsyncSession,
) -> None:
    result = await db_session.execute(
        text(
            "SELECT relname, relkind FROM pg_class "
            "JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace "
            "WHERE nspname = 'analytics' AND relname IN ('audit_entry', 'metric_event')"
        )
    )
    rows = {row[0]: row[1] for row in result}
    assert rows.get("audit_entry") == b"p"  # 'p' = partitioned table
    assert rows.get("metric_event") == b"p"

    result = await db_session.execute(
        text(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = 'analytics.audit_entry'::regclass "
            "AND NOT tgisinternal"
        )
    )
    assert "trg_audit_entry_immutability" in {row[0] for row in result}

    result = await db_session.execute(
        text(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = 'analytics.metric_event'::regclass "
            "AND NOT tgisinternal"
        )
    )
    assert "trg_metric_event_immutability" in {row[0] for row in result}

    result = await db_session.execute(
        text(
            "SELECT inhrelid::regclass::text FROM pg_inherits "
            "WHERE inhparent = 'analytics.audit_entry'::regclass"
        )
    )
    partitions = {row[0] for row in result}
    assert len(partitions) >= 3
