"""FastAPI router implementing exactly the 3 notifications-tagged OpenAPI operations
(`contracts/openapi.yaml`): `listNotifications`, `setNotificationRead`,
`markAllNotificationsRead`. Thin translation only: query/path/body -> use case call -> domain
object -> already-frozen `interfaces/dto.py` DTO. All business logic lives in
`application`/`domain`; this module owns none. Preference management (`updatePreferences`) is
identity's own operation (tagged `Users`, `PUT /me/preferences`) -- notifications owns no
preference-writing endpoint at all, only reads preferences via its own `RecipientDirectoryPort`
bridge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from notifications.application import NotificationUseCases
from notifications.domain import Notification as NotificationAggregate
from notifications.interfaces.auth import ActingUser
from notifications.interfaces.di import get_acting_user, get_notification_use_cases
from notifications.interfaces.dto import (
    Notification as NotificationDto,
)
from notifications.interfaces.dto import (
    NotificationPage,
    NotificationReadRequest,
    PageInfo,
)

notifications_router = APIRouter(tags=["Notifications"])


def _clamp_limit(limit: int | None) -> int:
    return min(max(limit or 20, 1), 100)


def _to_dto(notification: NotificationAggregate) -> NotificationDto:
    return NotificationDto(
        id=notification.id,
        event_key=notification.event_key,
        channel=notification.channel.value,
        subject=notification.rendered_subject,
        body=notification.rendered_body,
        read_at=notification.read_at,
        delivery_status=notification.delivery_status.value,
        created_at=notification.created_at,
    )


@notifications_router.get("/me/notifications", operation_id="listNotifications")
async def list_notifications(
    unreadOnly: bool | None = Query(default=False),
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    user: ActingUser = Depends(get_acting_user),
    use_cases: NotificationUseCases = Depends(get_notification_use_cases),
) -> NotificationPage:
    page_limit = _clamp_limit(limit)
    notifications, next_cursor = await use_cases.list_notifications(
        user.account_id.value,
        unread_only=bool(unreadOnly),
        cursor=cursor,
        limit=page_limit,
    )
    return NotificationPage(
        items=[_to_dto(n) for n in notifications],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


@notifications_router.put(
    "/me/notifications/{notificationId}/read", operation_id="setNotificationRead"
)
async def set_notification_read(
    notificationId: UUID,
    body: NotificationReadRequest,
    user: ActingUser = Depends(get_acting_user),
    use_cases: NotificationUseCases = Depends(get_notification_use_cases),
) -> NotificationDto:
    notification = await use_cases.set_notification_read(
        notificationId,
        recipient_user_id=user.account_id.value,
        read=body.read,
        now=datetime.now(UTC),
    )
    return _to_dto(notification)


@notifications_router.post(
    "/me/notifications/read-all",
    operation_id="markAllNotificationsRead",
    status_code=204,
)
async def mark_all_notifications_read(
    user: ActingUser = Depends(get_acting_user),
    use_cases: NotificationUseCases = Depends(get_notification_use_cases),
) -> None:
    await use_cases.mark_all_notifications_read(user.account_id.value, now=datetime.now(UTC))
