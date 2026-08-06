"""notifications -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from notifications.interfaces.dto import (
    Notification,
    NotificationPage,
    NotificationReadRequest,
)


class NotificationPort(Protocol):
    """Derived from OpenAPI operations: `listNotifications`, `markAllNotificationsRead`, `setNotificationRead`."""

    async def list_notifications(
        self,
        cursor: str | None = None,
        limit: int | None = 20,
        unread_only: bool | None = False,
    ) -> NotificationPage:
        """`GET /me/notifications` (operationId `listNotifications`). List my notifications"""
        ...

    async def mark_all_notifications_read(self) -> None:
        """`POST /me/notifications/read-all` (operationId `markAllNotificationsRead`). Mark all notifications read"""
        ...

    async def set_notification_read(
        self, notification_id: UUID, body: NotificationReadRequest
    ) -> Notification:
        """`PUT /me/notifications/{notificationId}/read` (operationId `setNotificationRead`). Set notification read status"""
        ...
