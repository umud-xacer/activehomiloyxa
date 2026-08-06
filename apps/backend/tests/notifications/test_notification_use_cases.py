"""`notifications.application.NotificationUseCases` (Task P-13) -- exercised against the
in-memory fake in `conftest.py`. Covers list/read/mark-read and the "own notifications only"
ownership scoping (a notification belonging to another recipient is indistinguishable from one
that does not exist -- both raise `NotificationNotFoundError`)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from notifications.application.exceptions import NotificationNotFoundError
from notifications.application.notification_use_cases import NotificationUseCases
from notifications.domain import Channel, Notification

from .conftest import FakeNotificationRepository

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _use_cases(fake_notifications: FakeNotificationRepository) -> NotificationUseCases:
    return NotificationUseCases(notifications=fake_notifications)


def _seed(
    fake_notifications: FakeNotificationRepository,
    recipient_user_id: object,
    **overrides: object,
) -> Notification:
    defaults: dict[str, object] = {
        "notification_id": uuid4(),
        "recipient_user_id": recipient_user_id,
        "event_key": "UserRegistered",
        "channel": Channel.EMAIL,
        "template_id": uuid4(),
        "template_version_id": uuid4(),
        "locale": "uz_latn",
        "rendered_subject": "Welcome",
        "rendered_body": "Welcome",
        "now": NOW,
    }
    defaults.update(overrides)
    notification = Notification.create(**defaults)  # type: ignore[arg-type]
    fake_notifications.rows[notification.id] = notification
    return notification


@pytest.mark.asyncio
async def test_list_notifications_only_returns_own(
    fake_notifications: FakeNotificationRepository,
) -> None:
    owner = uuid4()
    other = uuid4()
    mine = _seed(fake_notifications, owner)
    _seed(fake_notifications, other)

    use_cases = _use_cases(fake_notifications)
    items, _ = await use_cases.list_notifications(owner, unread_only=False, cursor=None, limit=20)

    assert [n.id for n in items] == [mine.id]


@pytest.mark.asyncio
async def test_list_notifications_unread_only_filters_read_ones(
    fake_notifications: FakeNotificationRepository,
) -> None:
    owner = uuid4()
    unread = _seed(fake_notifications, owner)
    read = _seed(fake_notifications, owner)
    fake_notifications.rows[read.id] = read.mark_read(now=NOW)

    use_cases = _use_cases(fake_notifications)
    items, _ = await use_cases.list_notifications(owner, unread_only=True, cursor=None, limit=20)

    assert [n.id for n in items] == [unread.id]


@pytest.mark.asyncio
async def test_get_notification_owned_by_another_user_raises_not_found(
    fake_notifications: FakeNotificationRepository,
) -> None:
    owner = uuid4()
    other = uuid4()
    theirs = _seed(fake_notifications, other)

    use_cases = _use_cases(fake_notifications)
    with pytest.raises(NotificationNotFoundError):
        await use_cases.get_notification(theirs.id, recipient_user_id=owner)


@pytest.mark.asyncio
async def test_get_nonexistent_notification_raises_not_found(
    fake_notifications: FakeNotificationRepository,
) -> None:
    use_cases = _use_cases(fake_notifications)
    with pytest.raises(NotificationNotFoundError):
        await use_cases.get_notification(uuid4(), recipient_user_id=uuid4())


@pytest.mark.asyncio
async def test_set_notification_read_true_then_false(
    fake_notifications: FakeNotificationRepository,
) -> None:
    owner = uuid4()
    mine = _seed(fake_notifications, owner)
    use_cases = _use_cases(fake_notifications)

    marked_read = await use_cases.set_notification_read(
        mine.id, recipient_user_id=owner, read=True, now=NOW
    )
    assert marked_read.read_at == NOW

    marked_unread = await use_cases.set_notification_read(
        mine.id, recipient_user_id=owner, read=False, now=NOW
    )
    assert marked_unread.read_at is None


@pytest.mark.asyncio
async def test_set_notification_read_refuses_someone_elses_notification(
    fake_notifications: FakeNotificationRepository,
) -> None:
    owner = uuid4()
    other = uuid4()
    theirs = _seed(fake_notifications, other)
    use_cases = _use_cases(fake_notifications)

    with pytest.raises(NotificationNotFoundError):
        await use_cases.set_notification_read(
            theirs.id, recipient_user_id=owner, read=True, now=NOW
        )


@pytest.mark.asyncio
async def test_mark_all_notifications_read_only_touches_own_unread(
    fake_notifications: FakeNotificationRepository,
) -> None:
    owner = uuid4()
    other = uuid4()
    mine_1 = _seed(fake_notifications, owner)
    mine_2 = _seed(fake_notifications, owner)
    theirs = _seed(fake_notifications, other)

    use_cases = _use_cases(fake_notifications)
    marked = await use_cases.mark_all_notifications_read(owner, now=NOW)

    assert marked == 2
    assert fake_notifications.rows[mine_1.id].read_at == NOW
    assert fake_notifications.rows[mine_2.id].read_at == NOW
    assert fake_notifications.rows[theirs.id].read_at is None
