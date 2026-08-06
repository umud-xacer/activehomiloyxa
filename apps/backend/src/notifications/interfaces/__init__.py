"""notifications.interfaces -- the module's only importable public surface (AIR-02)."""

from __future__ import annotations

from notifications.interfaces.dto import (
    Notification,
    NotificationPage,
    NotificationReadRequest,
)
from notifications.interfaces.ports import (
    NotificationPort,
)

__all__ = [
    "Notification",
    "NotificationPage",
    "NotificationPort",
    "NotificationReadRequest",
]
