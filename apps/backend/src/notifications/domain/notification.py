"""notifications -- the `Notification` aggregate (DDD Sec 5.10 `AR: Notification [P]`).
Persistence-ignorant, mirrors `moderation.domain.moderation_case.ModerationCase`'s style: frozen
dataclass, every transition returns a new instance via `dataclasses.replace`, guarded by a typed
exception raised before the replace. No setters -- delivery status only ever advances through
`mark_sent`/`mark_failed`, both legal only from `QUEUED` (a delivery attempt happens once; a
retry is a fresh dispatch attempt bumping `attempts`, orchestrated by the application layer, not
a second domain transition on the same row). `mark_read`/`mark_unread` are independent of
delivery status -- an in-app "read" flag the recipient controls regardless of whether the
underlying channel delivery succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from notifications.domain.exceptions import IllegalNotificationStateTransitionError
from notifications.domain.value_objects import Channel, DeliveryStatus


@dataclass(frozen=True)
class Notification:
    id: UUID
    recipient_user_id: UUID
    event_key: str
    channel: Channel
    template_id: UUID
    template_version_id: UUID
    locale: str
    rendered_subject: str | None
    rendered_body: str
    delivery_status: DeliveryStatus
    attempts: int
    provider_message_ref: str | None
    sent_at: datetime | None
    read_at: datetime | None
    created_at: datetime

    @staticmethod
    def create(
        *,
        notification_id: UUID,
        recipient_user_id: UUID,
        event_key: str,
        channel: Channel,
        template_id: UUID,
        template_version_id: UUID,
        locale: str,
        rendered_subject: str | None,
        rendered_body: str,
        now: datetime,
    ) -> Notification:
        """FR-NOTIF-001/002: a resolved (event, channel, recipient) triple that passed the
        preference check becomes exactly one `Notification` row, `QUEUED`, with its content
        already frozen (Physical DB: "frozen at dispatch (no live template dependency)") -- a
        later template edit in `configuration` never mutates an already-created notification."""
        return Notification(
            id=notification_id,
            recipient_user_id=recipient_user_id,
            event_key=event_key,
            channel=channel,
            template_id=template_id,
            template_version_id=template_version_id,
            locale=locale,
            rendered_subject=rendered_subject,
            rendered_body=rendered_body,
            delivery_status=DeliveryStatus.QUEUED,
            attempts=0,
            provider_message_ref=None,
            sent_at=None,
            read_at=None,
            created_at=now,
        )

    def _guard_from_queued(self, transition: str) -> None:
        if self.delivery_status is not DeliveryStatus.QUEUED:
            raise IllegalNotificationStateTransitionError(transition, self.delivery_status.value)

    def mark_sent(self, *, provider_message_ref: str | None, now: datetime) -> Notification:
        """The channel adapter's own provider call succeeded (Playbook Sec 6: happens OUTSIDE
        any open DB transaction -- this method only records the already-completed outcome).
        `provider_message_ref` is the OPAQUE provider identifier (Eskiz message id / email
        provider message id / web-push subscription endpoint) -- never a provider SDK type."""
        self._guard_from_queued("mark_sent")
        return replace(
            self,
            delivery_status=DeliveryStatus.SENT,
            attempts=self.attempts + 1,
            provider_message_ref=provider_message_ref,
            sent_at=now,
        )

    def mark_failed(self, *, now: datetime) -> Notification:
        """The channel adapter's own provider call failed (missing credentials, provider error,
        timeout) -- fails closed: recorded as `FAILED`, never silently retried on a different
        channel and never left `QUEUED` forever."""
        self._guard_from_queued("mark_failed")
        return replace(self, delivery_status=DeliveryStatus.FAILED, attempts=self.attempts + 1)

    def mark_read(self, *, now: datetime) -> Notification:
        """`setNotificationRead`/`markAllNotificationsRead` -- independent of `delivery_status`;
        idempotent (marking an already-read notification read again is a no-op, not an error)."""
        if self.read_at is not None:
            return self
        return replace(self, read_at=now)

    def mark_unread(self) -> Notification:
        if self.read_at is None:
            return self
        return replace(self, read_at=None)
