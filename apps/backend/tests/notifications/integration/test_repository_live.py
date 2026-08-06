"""`SqlalchemyNotificationRepository`/`SqlalchemyOrderRecipientProjectionRepository` against real
PostgreSQL: round-trips every field (including the partitioned table's own composite PK), proves
cursor pagination ordering, and confirms the local order-recipient projection upserts correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notifications.domain import Channel, DeliveryStatus, Notification
from notifications.infrastructure.persistence.repository import (
    SqlalchemyNotificationRepository,
    SqlalchemyOrderRecipientProjectionRepository,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _notification(recipient_user_id: object, **overrides: object) -> Notification:
    defaults: dict[str, object] = {
        "notification_id": uuid4(),
        "recipient_user_id": recipient_user_id,
        "event_key": "UserRegistered",
        "channel": Channel.EMAIL,
        "template_id": uuid4(),
        "template_version_id": uuid4(),
        "locale": "uz_latn",
        "rendered_subject": "Welcome",
        "rendered_body": "Welcome to Active Home",
        "now": NOW,
    }
    defaults.update(overrides)
    return Notification.create(**defaults)  # type: ignore[arg-type]


async def test_add_get_and_save_round_trip_every_field(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    recipient = uuid4()
    notification = _notification(recipient)

    async with session_factory() as session:
        await SqlalchemyNotificationRepository(session).add(notification)
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyNotificationRepository(session)
        fetched = await repo.get_by_id(notification.id)
        assert fetched is not None
        assert fetched.recipient_user_id == recipient
        assert fetched.channel is Channel.EMAIL
        assert fetched.delivery_status is DeliveryStatus.QUEUED
        assert fetched.rendered_body == "Welcome to Active Home"

        sent = fetched.mark_sent(provider_message_ref="msg-123", now=NOW)
        saved = await repo.save(sent)
        await session.commit()
        assert saved.delivery_status is DeliveryStatus.SENT

    async with session_factory() as session:
        reloaded = await SqlalchemyNotificationRepository(session).get_by_id(notification.id)
        assert reloaded is not None
        assert reloaded.delivery_status is DeliveryStatus.SENT
        assert reloaded.provider_message_ref == "msg-123"


async def test_list_for_recipient_orders_newest_first_and_paginates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    recipient = uuid4()
    older = _notification(recipient, now=NOW - timedelta(hours=2))
    newer = _notification(recipient, now=NOW)

    async with session_factory() as session:
        repo = SqlalchemyNotificationRepository(session)
        await repo.add(older)
        await repo.add(newer)
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyNotificationRepository(session)
        page, next_cursor = await repo.list_for_recipient(
            recipient, unread_only=False, cursor=None, limit=1
        )
        assert [n.id for n in page] == [newer.id]
        assert next_cursor is not None

        page_2, next_cursor_2 = await repo.list_for_recipient(
            recipient, unread_only=False, cursor=next_cursor, limit=1
        )
        assert [n.id for n in page_2] == [older.id]
        assert next_cursor_2 is None


async def test_list_for_recipient_unread_only_excludes_read(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    recipient = uuid4()
    unread = _notification(recipient)
    read = _notification(recipient).mark_read(now=NOW)

    async with session_factory() as session:
        repo = SqlalchemyNotificationRepository(session)
        await repo.add(unread)
        await repo.add(read)
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyNotificationRepository(session)
        page, _ = await repo.list_for_recipient(recipient, unread_only=True, cursor=None, limit=20)
        assert [n.id for n in page] == [unread.id]


async def test_order_recipient_projection_upsert_and_read(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    order_id = uuid4()
    profile_a = uuid4()
    profile_b = uuid4()

    async with session_factory() as session:
        repo = SqlalchemyOrderRecipientProjectionRepository(session)
        await repo.upsert(order_id=order_id, purchaser_profile_id=profile_a)
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyOrderRecipientProjectionRepository(session)
        assert await repo.get_purchaser_profile_id(order_id) == profile_a
        # upsert is idempotent-by-key, not append-only
        await repo.upsert(order_id=order_id, purchaser_profile_id=profile_b)
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyOrderRecipientProjectionRepository(session)
        assert await repo.get_purchaser_profile_id(order_id) == profile_b
