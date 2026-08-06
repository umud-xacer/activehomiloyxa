"""Integration test: `PartitionPrecreateWorker` against real PostgreSQL -- the migration itself
already precreates a few months of partitions at deploy time (`test_migration_smoke.py`); this
proves the ONGOING scheduled job also creates upcoming partitions correctly (Physical DB Sec 2/
Sec 16), idempotently.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics.infrastructure.partition_worker import PartitionPrecreateWorker


async def _partition_names(session: AsyncSession, table: str) -> set[str]:
    result = await session.execute(
        text(
            "SELECT inhrelid::regclass::text FROM pg_inherits "
            f"WHERE inhparent = 'analytics.{table}'::regclass"
        )
    )
    return {row[0].removeprefix("analytics.") for row in result}


async def test_run_once_creates_upcoming_partitions_for_a_far_future_month(
    db_session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The migration only precreates a few months from ITS OWN run date -- picking a month far
    enough in the future proves the WORKER (not just the migration) is what creates it."""
    # Partitions are cold storage, never dropped (Physical DB Sec 3.12) -- the shared dev
    # database may already carry this partition from a previous run, so this test only asserts
    # AFTER state (which IF NOT EXISTS makes correct regardless), never a "didn't exist before"
    # precondition.
    worker = PartitionPrecreateWorker(session_factory=session_factory, months_ahead=1)
    far_future = datetime(2030, 3, 15, tzinfo=UTC)

    executed = await worker.run_once(now=far_future)
    assert executed == 2  # one per table (audit_entry, metric_event), months_ahead=1

    after = await _partition_names(db_session, "audit_entry")
    assert "audit_entry_2030_03" in after
    metric_after = await _partition_names(db_session, "metric_event")
    assert "metric_event_2030_03" in metric_after


async def test_run_once_is_idempotent(
    db_session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    worker = PartitionPrecreateWorker(session_factory=session_factory, months_ahead=1)
    moment = datetime(2031, 6, 1, tzinfo=UTC)

    first = await worker.run_once(now=moment)
    second = await worker.run_once(now=moment)
    assert first == second == 2

    after = await _partition_names(db_session, "audit_entry")
    assert "audit_entry_2031_06" in after
