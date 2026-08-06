"""SQLAlchemy models for notifications' Postgres-backed `Notification` aggregate (Physical DB
Sec 2.10 `notifications.notification`, monthly RANGE-partitioned, PD-04) and the local
`order_recipient_projection` (not in the documented Physical Database Design -- a "locally
necessary addition", the same precedent `catalog.subscription_projection`/`profiles.
verification_entitlement_projection` already established).

`NotificationRow` deliberately does NOT use `backbone.persistence.AggregateMixin`: a
RANGE-partitioned table's primary key must include the partition key column (`created_at`), so
the PK here is the composite `(id, created_at)` the Physical DB Design itself specifies, not
`AggregateMixin`'s own single-column `id` PK. No `lock_version`/optimistic locking either -- the
documented physical schema has none (this aggregate is single-writer-per-row: created once
`QUEUED`, updated at most once more to `SENT`/`FAILED`/read-status, never concurrently
contended).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Index,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backbone.idempotency import make_processed_event_model
from notifications.infrastructure.persistence.base import NotificationsBase

_CHANNELS = "('EMAIL', 'WEB_PUSH', 'SMS')"
_LOCALES = "('uz_latn', 'uz_cyrl', 'ru', 'en')"
_DELIVERY_STATUSES = "('QUEUED', 'SENT', 'DELIVERED', 'FAILED')"


class NotificationRow(NotificationsBase):  # type: ignore[misc,valid-type]
    __tablename__ = "notification"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )
    recipient_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_key: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    template_version_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    rendered_body: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="QUEUED")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    provider_message_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    """Not in the documented Physical Database Design's own `notification` column list -- but the
    already-frozen `contracts/openapi.yaml` `Notification.readAt`/`NotificationReadRequest`/
    `setNotificationRead`/`markAllNotificationsRead` operations (Task P-01) require it; a
    "locally necessary addition" serving an already-frozen contract, the same class of gap
    `profiles`'s own local projection table already resolved without needing an ADR."""

    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at", name="pk_notification"),
        CheckConstraint(f"channel IN {_CHANNELS}", name="ck_notification_channel"),
        CheckConstraint(f"locale IN {_LOCALES}", name="ck_notification_locale"),
        CheckConstraint(
            f"delivery_status IN {_DELIVERY_STATUSES}",
            name="ck_notification_delivery_status",
        ),
        Index("ix_notification_recipient", "recipient_user_id", "created_at"),
    )


class OrderRecipientProjectionRow(NotificationsBase):  # type: ignore[misc,valid-type]
    __tablename__ = "order_recipient_projection"

    order_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    purchaser_profile_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )


ProcessedEventRow: Any = make_processed_event_model(NotificationsBase)
"""notifications is a PURE event sink (X-08, SAD Sec 8.2: "nothing imports admin, analytics, or
notifications") -- it consumes idempotently via this ledger but never publishes its own domain
event, so unlike every other implemented module it has no `OutboxEventRow`/`OutboxWriter`."""
