"""notifications/application -- exceptions (Task P-13)."""

from __future__ import annotations

from uuid import UUID


class NotificationApplicationError(Exception):
    """Base for every typed exception raised by notifications' application/ layer."""


class RecipientMissingContactDetailError(NotificationApplicationError):
    """Raised by `NotificationDispatchUseCases._send()` when the queued dispatch's channel has
    no matching contact detail on the recipient snapshot -- `_preference_allows()` already
    requires this at queue time, so this only fires if the recipient's contact details changed
    between queueing and actual dispatch (e.g. the user cleared their email); `dispatch_queued`'s
    own "fails closed" contract catches this and marks the notification FAILED, never SENT."""

    def __init__(self, user_id: UUID, channel: str) -> None:
        self.user_id = user_id
        self.channel = channel
        super().__init__(f"recipient {user_id} has no contact detail for channel {channel!r}")


class NotificationNotFoundError(NotificationApplicationError):
    """Raised for both "does not exist" and "exists but is not this recipient's own" -- the
    repository query is always scoped to `recipient_user_id`, so the two cases are
    indistinguishable by construction (never leaks whether another user's notification exists,
    the same secure-by-construction pattern `getListing`'s own 404-not-403 precedent uses)."""

    def __init__(self, notification_id: UUID) -> None:
        self.notification_id = notification_id
        super().__init__(f"notification {notification_id} not found")
