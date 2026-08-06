"""analytics/application -- ports (repository/projection interfaces). `infrastructure/` provides
the concrete adapters; `application/` depends only on these `Protocol`s (DIP, Absolute
Architecture Rule 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from analytics.domain import AuditEntry, MetricEvent, MetricKey
from shared_kernel import ListingId


class AuditEntryRepository(Protocol):
    """Append-only (`add` only -- no `save`/`update` method exists on this Protocol at all, so
    the application layer cannot even attempt to mutate a stored fact)."""

    async def add(self, entry: AuditEntry) -> None: ...

    async def query(
        self,
        *,
        actor_user_id: UUID | None,
        target_type: str | None,
        action: str | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[AuditEntry], str | None]:
        """FR-AUDIT-002: filterable, cursor-paginated."""
        ...

    async def list_for_report(
        self,
        *,
        actions: tuple[str, ...],
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> list[AuditEntry]:
        """Unpaginated scan backing `OperationalReport` datasets (FR-ADMIN-005) -- v1 reports are
        "basic" (BRULE-20/DEC-06), not a BI aggregation engine, so a bounded date-range scan is
        the documented ceiling, not a shortcut."""
        ...


class MetricEventRepository(Protocol):
    """Append-only (`add` only)."""

    async def add(self, event: MetricEvent) -> None: ...

    async def list_for_report(
        self,
        *,
        metric_keys: tuple[MetricKey, ...],
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> list[MetricEvent]:
        """Backs `LISTINGS_OVERVIEW` (FR-ADMIN-005)."""
        ...

    async def list_all_ordered(self) -> list[MetricEvent]:
        """Every `MetricEvent`, ordered `(occurred_at, id)` -- the full replay stream the
        `ListingStatistics` projection rebuild scans from position zero (DB Architecture Sec
        3.12: "read models... may be discarded and reprojected")."""
        ...


@dataclass(frozen=True)
class ListingStatisticsSnapshot:
    """`analytics.listing_statistics` row shape (FR-ANALYTICS-002) -- a rebuildable projection,
    not an aggregate: no invariants beyond idempotent upsert."""

    listing_id: ListingId
    views: int
    contact_clicks: int
    phone_reveals: int
    chats_initiated: int
    favorites: int
    as_of_position: int
    updated_at: datetime


class ListingStatisticsProjectionRepository(Protocol):
    """Owned entirely by analytics; derived, no invariants (DB Architecture Sec 3.12)."""

    async def get_by_listing_id(
        self, listing_id: ListingId
    ) -> ListingStatisticsSnapshot | None: ...

    async def apply_metric(self, metric: MetricEvent, *, position: int) -> None:
        """Increments the one counter `metric.metric_key` maps to for `metric.listing_id`
        (a no-op for metric families with no `listing_id`, e.g. banner metrics) and advances
        `as_of_position`. Idempotent re-application at the SAME position is not itself guarded
        here -- the caller (the event consumer, keyed on `source_event_id` via `ProcessedEvent`)
        is what makes the overall pipeline exactly-once (I-23)."""
        ...

    async def reset(self) -> None:
        """Wipes every row -- the destructive half of "discard the projection, replay the
        MetricEvent stream, and assert the projection is reconstructed identically"."""
        ...

    async def checkpoint_position(self) -> int:
        """0 when the projection has never been built/was just reset."""
        ...

    async def advance_checkpoint(self, position: int) -> None: ...


# Deliberately absent: any port resolving an actor/target ref by calling another module.
# Absolute Architecture Rule 1 confines analytics to `shared_kernel` -- every port above stores
# and returns exactly what the triggering event's own payload carried. See `analytics/README.md`
# "No-dereference guarantee" and `test_boundary_import.py`.
