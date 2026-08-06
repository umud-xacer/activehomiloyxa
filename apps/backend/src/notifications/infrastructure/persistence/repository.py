"""`SqlalchemyNotificationRepository`/`SqlalchemyOrderRecipientProjectionRepository` -- implement
`application.ports`' repositories against Postgres. Maps the persistence-ignorant `Notification`
aggregate to/from its ORM row (DB Architecture Sec 18 "mapping lives in infrastructure/").
"""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notifications.domain import Channel, DeliveryStatus, Notification
from notifications.infrastructure.persistence.models import (
    NotificationRow,
    OrderRecipientProjectionRow,
)


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id)


def _to_domain(row: NotificationRow) -> Notification:
    return Notification(
        id=row.id,
        recipient_user_id=row.recipient_user_id,
        event_key=row.event_key,
        channel=Channel(row.channel),
        template_id=row.template_id,
        template_version_id=row.template_version_id,
        locale=row.locale,
        rendered_subject=row.rendered_subject,
        rendered_body=row.rendered_body,
        delivery_status=DeliveryStatus(row.delivery_status),
        attempts=row.attempts,
        provider_message_ref=row.provider_message_ref,
        sent_at=row.sent_at,
        read_at=row.read_at,
        created_at=row.created_at,
    )


def _apply_fields(row: NotificationRow, notification: Notification) -> None:
    row.recipient_user_id = notification.recipient_user_id
    row.event_key = notification.event_key
    row.channel = notification.channel.value
    row.template_id = notification.template_id
    row.template_version_id = notification.template_version_id
    row.locale = notification.locale
    row.rendered_subject = notification.rendered_subject
    row.rendered_body = notification.rendered_body
    row.delivery_status = notification.delivery_status.value
    row.attempts = notification.attempts
    row.provider_message_ref = notification.provider_message_ref
    row.sent_at = notification.sent_at
    row.read_at = notification.read_at


class SqlalchemyNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification) -> None:
        row = NotificationRow(id=notification.id, created_at=notification.created_at)
        _apply_fields(row, notification)
        self._session.add(row)
        await self._session.flush()

    async def save(self, notification: Notification) -> Notification:
        row = await self._get_row(notification.id)
        if row is None:
            raise LookupError(f"NotificationRow {notification.id} not found for save()")
        _apply_fields(row, notification)
        await self._session.flush()
        return _to_domain(row)

    async def get_by_id(self, notification_id: UUID) -> Notification | None:
        row = await self._get_row(notification_id)
        return _to_domain(row) if row is not None else None

    async def _get_row(self, notification_id: UUID) -> NotificationRow | None:
        # `NotificationRow`'s own PK is the composite `(id, created_at)` (a RANGE-partitioned
        # table's PK must include the partition key) -- `session.get()` needs the full PK
        # tuple, so a plain `id`-only lookup uses a SELECT instead.
        result = await self._session.execute(
            select(NotificationRow).where(NotificationRow.id == notification_id)
        )
        return result.scalars().first()

    async def list_for_recipient(
        self,
        recipient_user_id: UUID,
        *,
        unread_only: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Notification], str | None]:
        stmt = (
            select(NotificationRow)
            .where(NotificationRow.recipient_user_id == recipient_user_id)
            .order_by(NotificationRow.created_at.desc(), NotificationRow.id.desc())
            .limit(limit + 1)
        )
        if unread_only:
            stmt = stmt.where(NotificationRow.read_at.is_(None))
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (NotificationRow.created_at < created_at)
                | ((NotificationRow.created_at == created_at) & (NotificationRow.id < row_id))
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
        return [_to_domain(row) for row in rows], next_cursor


class SqlalchemyOrderRecipientProjectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, *, order_id: UUID, purchaser_profile_id: UUID) -> None:
        row = await self._session.get(OrderRecipientProjectionRow, order_id)
        if row is None:
            self._session.add(
                OrderRecipientProjectionRow(
                    order_id=order_id, purchaser_profile_id=purchaser_profile_id
                )
            )
        else:
            row.purchaser_profile_id = purchaser_profile_id
        await self._session.flush()

    async def get_purchaser_profile_id(self, order_id: UUID) -> UUID | None:
        row = await self._session.get(OrderRecipientProjectionRow, order_id)
        return row.purchaser_profile_id if row is not None else None
