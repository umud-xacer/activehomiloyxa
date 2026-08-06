"""Shared fixtures for `analytics`'s fast (no-DB) unit + API tests: in-memory fakes for every
port `application/ports.py` declares, mirroring `apps/backend/tests/ads/conftest.py`'s pattern
exactly.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest

from analytics.application.ports import ListingStatisticsSnapshot
from analytics.domain import AuditEntry, MetricEvent, MetricKey
from shared_kernel import ListingId


def _encode_cursor(occurred_at: datetime, row_id: UUID) -> str:
    raw = f"{occurred_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    occurred_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(occurred_at_str), UUID(row_id)


@dataclass
class FakeAuditEntryRepository:
    """Implements `analytics.application.ports.AuditEntryRepository`."""

    entries: list[AuditEntry] = field(default_factory=list)

    async def add(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

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
        items = sorted(self.entries, key=lambda e: (e.occurred_at, e.id))
        if actor_user_id is not None:
            items = [e for e in items if e.actor_user_id and e.actor_user_id.value == actor_user_id]
        if target_type is not None:
            items = [e for e in items if e.target_type == target_type]
        if action is not None:
            items = [e for e in items if e.action == action]
        if occurred_from is not None:
            items = [e for e in items if e.occurred_at >= occurred_from]
        if occurred_to is not None:
            items = [e for e in items if e.occurred_at <= occurred_to]
        if cursor is not None:
            occurred_at, row_id = _decode_cursor(cursor)
            items = [e for e in items if (e.occurred_at, e.id) > (occurred_at, row_id)]
        page = items[: limit + 1]
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = _encode_cursor(page[-1].occurred_at, page[-1].id)
        return page, next_cursor

    async def list_for_report(
        self,
        *,
        actions: tuple[str, ...],
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> list[AuditEntry]:
        items = [e for e in self.entries if e.action in actions]
        if occurred_from is not None:
            items = [e for e in items if e.occurred_at >= occurred_from]
        if occurred_to is not None:
            items = [e for e in items if e.occurred_at <= occurred_to]
        return items


@dataclass
class FakeMetricEventRepository:
    """Implements `analytics.application.ports.MetricEventRepository`."""

    events: list[MetricEvent] = field(default_factory=list)

    async def add(self, event: MetricEvent) -> None:
        self.events.append(event)

    async def list_for_report(
        self,
        *,
        metric_keys: tuple[MetricKey, ...],
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> list[MetricEvent]:
        items = [e for e in self.events if e.metric_key in metric_keys]
        if occurred_from is not None:
            items = [e for e in items if e.occurred_at >= occurred_from]
        if occurred_to is not None:
            items = [e for e in items if e.occurred_at <= occurred_to]
        return items

    async def list_all_ordered(self) -> list[MetricEvent]:
        return sorted(self.events, key=lambda e: (e.occurred_at, e.id))


_COUNTER_BY_METRIC = {
    MetricKey.LISTING_VIEWED: "views",
    MetricKey.CONTACT_BUTTON_CLICKED: "contact_clicks",
    MetricKey.CHAT_INITIATED: "chats_initiated",
    MetricKey.FAVORITE_ADDED: "favorites",
}


@dataclass
class FakeListingStatisticsProjectionRepository:
    """Implements `analytics.application.ports.ListingStatisticsProjectionRepository`."""

    rows: dict[UUID, dict[str, int]] = field(default_factory=dict)
    checkpoint: int = 0

    async def get_by_listing_id(self, listing_id: ListingId) -> ListingStatisticsSnapshot | None:
        row = self.rows.get(listing_id.value)
        if row is None:
            return None
        return ListingStatisticsSnapshot(
            listing_id=listing_id,
            views=row["views"],
            contact_clicks=row["contact_clicks"],
            phone_reveals=row["phone_reveals"],
            chats_initiated=row["chats_initiated"],
            favorites=row["favorites"],
            as_of_position=row["as_of_position"],
            updated_at=datetime.now(UTC),
        )

    async def apply_metric(self, metric: MetricEvent, *, position: int) -> None:
        counter = _COUNTER_BY_METRIC.get(metric.metric_key)
        if counter is None or metric.listing_id is None:
            return
        row = self.rows.setdefault(
            metric.listing_id.value,
            {
                "views": 0,
                "contact_clicks": 0,
                "phone_reveals": 0,
                "chats_initiated": 0,
                "favorites": 0,
                "as_of_position": 0,
            },
        )
        row[counter] += 1
        row["as_of_position"] = position

    async def reset(self) -> None:
        self.rows.clear()

    async def checkpoint_position(self) -> int:
        return self.checkpoint

    async def advance_checkpoint(self, position: int) -> None:
        self.checkpoint = position


@pytest.fixture
def fake_audit_entries() -> FakeAuditEntryRepository:
    return FakeAuditEntryRepository()


@pytest.fixture
def fake_metric_events() -> FakeMetricEventRepository:
    return FakeMetricEventRepository()


@pytest.fixture
def fake_listing_statistics() -> FakeListingStatisticsProjectionRepository:
    return FakeListingStatisticsProjectionRepository()
