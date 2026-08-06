"""Monthly RANGE-partition precreation (Physical DB Sec 2: "the three highest-volume append-only
tables ... are declaratively range-partitioned by month from day one"; Sec 16 "retro-fitting
partitioning is a rewrite, adopting it at creation is free" -- and its own corollary, a
partition-precreate job so a table is never caught without an upcoming month's partition).

Pure DDL generation, mirroring `guard_trigger.py`'s own style exactly (validated identifiers,
returns SQL strings, no I/O) -- the caller executes each string on its own connection. First real
consumer: `analytics.infrastructure.partition_worker` (`analytics.audit_entry`/
`analytics.metric_event`, Task P-15); `notifications.notification` (Task P-13) is also monthly
RANGE-partitioned but was deliberately left on a single `DEFAULT` catch-all partition as an
explicitly out-of-scope deferral at the time -- reusable here for any future task that wants to
adopt real partition precreation for it too, without duplicating this DDL logic.
"""

from __future__ import annotations

from datetime import date

from backbone.migrations.guard_trigger import _validate


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def partition_name(table: str, year: int, month: int) -> str:
    _validate(table)
    return f"{table}_{year:04d}_{month:02d}"


def create_monthly_partition_ddl(schema: str, table: str, *, year: int, month: int) -> str:
    """`IF NOT EXISTS` -- precreation is idempotent; re-running the worker for a month whose
    partition already exists is a no-op, not an error."""
    _validate(schema, table)
    start, end = _month_bounds(year, month)
    part_name = partition_name(table, year, month)
    return (
        f'CREATE TABLE IF NOT EXISTS "{schema}"."{part_name}" '
        f'PARTITION OF "{schema}"."{table}" '
        f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
    )


def upcoming_month_partition_ddls(
    schema: str, table: str, *, from_year: int, from_month: int, months_ahead: int
) -> list[str]:
    """DDL for `months_ahead` consecutive months starting at `(from_year, from_month)`
    inclusive -- e.g. `months_ahead=3` from 2026-07 creates July, August, September."""
    if months_ahead < 1:
        raise ValueError("months_ahead must be at least 1")
    statements = []
    year, month = from_year, from_month
    for _ in range(months_ahead):
        statements.append(create_monthly_partition_ddl(schema, table, year=year, month=month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return statements
