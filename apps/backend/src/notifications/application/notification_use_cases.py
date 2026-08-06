"""notifications/application -- `NotificationUseCases` (Task P-13): the user-facing read/
read-status surface (`listNotifications`/`setNotificationRead`/`markAllNotificationsRead`).
Every query is scoped to the acting recipient's own `UserId` -- there is no cross-recipient read
path anywhere in this class (the "may read only their own notifications" requirement is enforced
structurally here, not via a permission key: every authenticated user has blanket rights to
their OWN notifications, mirroring catalog/media's own self-service ownership model rather than
an admin-gated one)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from notifications.application.exceptions import NotificationNotFoundError
from notifications.application.ports import NotificationRepository
from notifications.domain import Notification


class NotificationUseCases:
    def __init__(self, *, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def list_notifications(
        self,
        recipient_user_id: UUID,
        *,
        unread_only: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Notification], str | None]:
        return await self._notifications.list_for_recipient(
            recipient_user_id, unread_only=unread_only, cursor=cursor, limit=limit
        )

    async def get_notification(
        self, notification_id: UUID, *, recipient_user_id: UUID
    ) -> Notification:
        notification = await self._notifications.get_by_id(notification_id)
        if notification is None or notification.recipient_user_id != recipient_user_id:
            raise NotificationNotFoundError(notification_id)
        return notification

    async def set_notification_read(
        self,
        notification_id: UUID,
        *,
        recipient_user_id: UUID,
        read: bool,
        now: datetime,
    ) -> Notification:
        notification = await self.get_notification(
            notification_id, recipient_user_id=recipient_user_id
        )
        updated = notification.mark_read(now=now) if read else notification.mark_unread()
        return await self._notifications.save(updated)

    async def mark_all_notifications_read(self, recipient_user_id: UUID, *, now: datetime) -> int:
        marked = 0
        cursor: str | None = None
        while True:
            page, cursor = await self._notifications.list_for_recipient(
                recipient_user_id, unread_only=True, cursor=cursor, limit=50
            )
            if not page:
                break
            for notification in page:
                await self._notifications.save(notification.mark_read(now=now))
                marked += 1
            if cursor is None:
                break
        return marked
