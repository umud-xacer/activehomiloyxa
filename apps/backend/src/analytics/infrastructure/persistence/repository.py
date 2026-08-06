"""`SqlalchemyAuditEntryRepository`/`SqlalchemyMetricEventRepository`/
`SqlalchemyListingStatisticsProjectionRepository` -- implement `application.ports`'s
repositories against Postgres. `add()` is a plain `INSERT` (append-only, no `save()`/`update()`
method exists on either fact repository at all -- the immutability guarantee is structural, not
just policed by the database's own guard trigger). Mirrors `ads.infrastructure.persistence.
repository`'s cursor-pagination pattern.
"""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.application.ports import ListingStatisticsSnapshot
from analytics.domain import AuditEntry, MetricEvent, MetricKey
from analytics.infrastructure.persistence.models import (
    AuditEntryRow,
    ListingStatisticsRow,
    MetricEventRow,
    ProjectionCheckpointRow,
)
from shared_kernel import ListingId, UserId

_LISTING_STATISTICS_PROJECTION_NAME = "listing_statistics"

_METRIC_TO_COUNTER: dict[MetricKey, str] = {
    MetricKey.LISTING_VIEWED: "views",
    MetricKey.CONTACT_BUTTON_CLICKED: "contact_clicks",
    MetricKey.CHAT_INITIATED: "chats_initiated",
    MetricKey.FAVORITE_ADDED: "favorites",
}
"""`PHONE_REVEALED` is deliberately absent: messaging's existing `PhoneRevealed` payload carries
no `listingId` (only `conversationId`/`revealerUserId`/`revealedUserId`), so it can never update
a per-listing counter as currently shaped -- see `analytics/README.md` "Known gaps".
`PREMIUM_LISTING_STAT`/`BANNER_IMPRESSION_RECORDED`/`BANNER_CLICK_RECORDED` are absent because no
matching counter exists on `ListingStatistics` at all (Physical DB Sec 3.12's own column list)."""


def _encode_cursor(occurred_at: datetime, row_id: UUID) -> str:
    raw = f"{occurred_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    occurred_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(occurred_at_str), UUID(row_id)


def _audit_row_to_domain(row: AuditEntryRow) -> AuditEntry:
    return AuditEntry.create(
        entry_id=row.id,
        occurred_at=row.occurred_at,
        action=row.action,
        actor_user_id=UserId(value=row.actor_user_id) if row.actor_user_id else None,
        actor_context=row.actor_context,
        target_type=row.target_type,
        target_id=row.target_id,
        payload=row.payload,
        source_event_id=row.source_event_id,
    )


def _metric_row_to_domain(row: MetricEventRow) -> MetricEvent:
    return MetricEvent.create(
        event_id=row.id,
        occurred_at=row.occurred_at,
        metric_key=row.metric_key,
        listing_id=ListingId(value=row.listing_id) if row.listing_id else None,
        user_id=UserId(value=row.user_id) if row.user_id else None,
        campaign_id=row.campaign_id,
        payload=row.payload,
        source_event_id=row.source_event_id,
    )


class SqlalchemyAuditEntryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditEntry) -> None:
        self._session.add(
            AuditEntryRow(
                id=entry.id,
                occurred_at=entry.occurred_at,
                actor_user_id=entry.actor_user_id.value if entry.actor_user_id else None,
                actor_context=entry.actor_context,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                payload=entry.payload,
                source_event_id=entry.source_event_id,
            )
        )

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
        stmt = (
            select(AuditEntryRow)
            .order_by(AuditEntryRow.occurred_at, AuditEntryRow.id)
            .limit(limit + 1)
        )
        if actor_user_id is not None:
            stmt = stmt.where(AuditEntryRow.actor_user_id == actor_user_id)
        if target_type is not None:
            stmt = stmt.where(AuditEntryRow.target_type == target_type)
        if action is not None:
            stmt = stmt.where(AuditEntryRow.action == action)
        if occurred_from is not None:
            stmt = stmt.where(AuditEntryRow.occurred_at >= occurred_from)
        if occurred_to is not None:
            stmt = stmt.where(AuditEntryRow.occurred_at <= occurred_to)
        if cursor is not None:
            occurred_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (AuditEntryRow.occurred_at > occurred_at)
                | ((AuditEntryRow.occurred_at == occurred_at) & (AuditEntryRow.id > row_id))
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].occurred_at, rows[-1].id)
        return [_audit_row_to_domain(row) for row in rows], next_cursor

    async def list_for_report(
        self,
        *,
        actions: tuple[str, ...],
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> list[AuditEntry]:
        stmt = select(AuditEntryRow).where(AuditEntryRow.action.in_(actions))
        if occurred_from is not None:
            stmt = stmt.where(AuditEntryRow.occurred_at >= occurred_from)
        if occurred_to is not None:
            stmt = stmt.where(AuditEntryRow.occurred_at <= occurred_to)
        result = await self._session.execute(stmt)
        return [_audit_row_to_domain(row) for row in result.scalars().all()]


class SqlalchemyMetricEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: MetricEvent) -> None:
        self._session.add(
            MetricEventRow(
                id=event.id,
                occurred_at=event.occurred_at,
                metric_key=event.metric_key.value,
                listing_id=event.listing_id.value if event.listing_id else None,
                user_id=event.user_id.value if event.user_id else None,
                campaign_id=event.campaign_id,
                payload=event.payload,
                source_event_id=event.source_event_id,
            )
        )

    async def list_for_report(
        self,
        *,
        metric_keys: tuple[MetricKey, ...],
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> list[MetricEvent]:
        stmt = select(MetricEventRow).where(
            MetricEventRow.metric_key.in_([key.value for key in metric_keys])
        )
        if occurred_from is not None:
            stmt = stmt.where(MetricEventRow.occurred_at >= occurred_from)
        if occurred_to is not None:
            stmt = stmt.where(MetricEventRow.occurred_at <= occurred_to)
        result = await self._session.execute(stmt)
        return [_metric_row_to_domain(row) for row in result.scalars().all()]

    async def list_all_ordered(self) -> list[MetricEvent]:
        stmt = select(MetricEventRow).order_by(MetricEventRow.occurred_at, MetricEventRow.id)
        result = await self._session.execute(stmt)
        return [_metric_row_to_domain(row) for row in result.scalars().all()]


class SqlalchemyListingStatisticsProjectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_listing_id(self, listing_id: ListingId) -> ListingStatisticsSnapshot | None:
        row = await self._session.get(ListingStatisticsRow, listing_id.value)
        if row is None:
            return None
        return _listing_statistics_row_to_snapshot(row)

    async def apply_metric(self, metric: MetricEvent, *, position: int) -> None:
        counter_column = _METRIC_TO_COUNTER.get(metric.metric_key)
        if counter_column is None or metric.listing_id is None:
            return
        row = await self._session.get(ListingStatisticsRow, metric.listing_id.value)
        if row is None:
            # Explicit zeros rather than relying on the column's `server_default` -- that only
            # applies once the row round-trips through INSERT, but the counter increment below
            # reads the in-memory value immediately, before any flush.
            row = ListingStatisticsRow(
                listing_id=metric.listing_id.value,
                views=0,
                contact_clicks=0,
                phone_reveals=0,
                chats_initiated=0,
                favorites=0,
                as_of_position=0,
            )
            self._session.add(row)
        setattr(row, counter_column, getattr(row, counter_column) + 1)
        row.as_of_position = position

    async def reset(self) -> None:
        result = await self._session.execute(select(ListingStatisticsRow))
        for row in result.scalars().all():
            await self._session.delete(row)

    async def checkpoint_position(self) -> int:
        row = await self._session.get(ProjectionCheckpointRow, _LISTING_STATISTICS_PROJECTION_NAME)
        return row.last_position if row is not None else 0

    async def advance_checkpoint(self, position: int) -> None:
        row = await self._session.get(ProjectionCheckpointRow, _LISTING_STATISTICS_PROJECTION_NAME)
        if row is None:
            self._session.add(
                ProjectionCheckpointRow(
                    projection_name=_LISTING_STATISTICS_PROJECTION_NAME, last_position=position
                )
            )
        else:
            row.last_position = position


def _listing_statistics_row_to_snapshot(row: ListingStatisticsRow) -> ListingStatisticsSnapshot:
    return ListingStatisticsSnapshot(
        listing_id=ListingId(value=row.listing_id),
        views=row.views,
        contact_clicks=row.contact_clicks,
        phone_reveals=row.phone_reveals,
        chats_initiated=row.chats_initiated,
        favorites=row.favorites,
        as_of_position=row.as_of_position,
        updated_at=row.updated_at,
    )
