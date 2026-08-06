"""notifications/domain -- the Notification aggregate, value objects, and typed exceptions
(Task P-13). Imports `shared_kernel` only (Clean Architecture rule 1); never imported by another
module (`domain/` is never part of a module's public surface, AIR-02).
"""

from __future__ import annotations

from notifications.domain.exceptions import (
    IllegalNotificationStateTransitionError,
    NotificationDomainError,
    UnsupportedChannelError,
)
from notifications.domain.notification import Notification
from notifications.domain.value_objects import (
    TERMINAL_DELIVERY_STATUSES,
    Channel,
    DeliveryStatus,
    RecipientRef,
    RenderedContent,
)

__all__ = [
    "TERMINAL_DELIVERY_STATUSES",
    "Channel",
    "DeliveryStatus",
    "IllegalNotificationStateTransitionError",
    "Notification",
    "NotificationDomainError",
    "RecipientRef",
    "RenderedContent",
    "UnsupportedChannelError",
]
