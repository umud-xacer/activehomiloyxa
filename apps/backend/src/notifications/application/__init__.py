"""notifications/application -- use cases + ports (Task P-13). Depends only on `notifications.
domain`, `shared_kernel`."""

from __future__ import annotations

from notifications.application.dispatch_use_cases import (
    NotificationDispatchUseCases,
    QueuedDispatch,
)
from notifications.application.exceptions import (
    NotificationApplicationError,
    NotificationNotFoundError,
)
from notifications.application.notification_use_cases import NotificationUseCases
from notifications.application.ports import (
    EmailProviderPort,
    NotificationRepository,
    NotificationTemplateSnapshot,
    OrderRecipientProjectionRepository,
    RecipientDirectoryPort,
    RecipientSnapshot,
    SmsProviderPort,
    TemplateReaderPort,
    WebPushProviderPort,
    WebPushSubscriptionSnapshot,
)

__all__ = [
    "EmailProviderPort",
    "NotificationApplicationError",
    "NotificationDispatchUseCases",
    "NotificationNotFoundError",
    "NotificationRepository",
    "NotificationTemplateSnapshot",
    "NotificationUseCases",
    "OrderRecipientProjectionRepository",
    "QueuedDispatch",
    "RecipientDirectoryPort",
    "RecipientSnapshot",
    "SmsProviderPort",
    "TemplateReaderPort",
    "WebPushProviderPort",
    "WebPushSubscriptionSnapshot",
]
