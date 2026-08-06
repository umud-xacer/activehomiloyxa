"""The partition-precreate scheduled job (Physical DB Sec 2/Sec 16: monthly RANGE partitioning
for `analytics.audit_entry`/`analytics.metric_event`, "adopting it at creation is free" --
precreating the next few months' partitions so a table is never caught without one). Mirrors
`ads.infrastructure.worker.CampaignScheduleSweepWorker`'s `run_once()`/`run_forever(stop_event)`
poll-loop shape; uses `backbone.migrations.upcoming_month_partition_ddls` for the DDL itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from backbone.migrations import upcoming_month_partition_ddls
from backbone.persistence import session_scope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

_PARTITIONED_TABLES = ("audit_entry", "metric_event")


class PartitionPrecreateWorker:
    """Runs on a long interval (daily is more than enough -- partitions are monthly), not the
    fast poll cadence of an event-sweep worker."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        months_ahead: int = 3,
        poll_interval_seconds: float = 86_400.0,
    ) -> None:
        self._session_factory = session_factory
        self._months_ahead = months_ahead
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self, *, now: datetime | None = None) -> int:
        """Creates any of the next `months_ahead` months' partitions that don't already exist,
        for both `audit_entry` and `metric_event`, in one transaction. Idempotent (`IF NOT
        EXISTS`) -- safe to run as often as the schedule likes. Returns the number of `CREATE
        TABLE` statements executed (already-existing partitions still count -- `IF NOT EXISTS`
        makes re-creation a cheap no-op, not a skip)."""
        moment = now or datetime.now(UTC)
        executed = 0
        async with session_scope(self._session_factory) as session:
            for table in _PARTITIONED_TABLES:
                for ddl in upcoming_month_partition_ddls(
                    "analytics",
                    table,
                    from_year=moment.year,
                    from_month=moment.month,
                    months_ahead=self._months_ahead,
                ):
                    await session.execute(text(ddl))
                    executed += 1
        return executed

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("partition precreate batch failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)
