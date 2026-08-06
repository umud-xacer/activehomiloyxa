"""notifications -- value objects (DDD Sec 5.10 BC-10). Persistence-ignorant, mirrors
`moderation.domain.value_objects`'s style.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Channel(StrEnum):
    """DDD Sec 5.10 VO `Channel (Email/WebPush/Sms)` -- fixed, code-owned (DEC-18); matches
    `configuration.domain.whitelist.NOTIFICATION_CHANNELS` and the Physical DB Design's own
    `notification.channel` CHECK exactly."""

    EMAIL = "EMAIL"
    WEB_PUSH = "WEB_PUSH"
    SMS = "SMS"


class DeliveryStatus(StrEnum):
    """Physical DB Design's own `notification.delivery_status` CHECK -- no `SUPPRESSED` member
    exists: a preference-suppressed delivery never becomes a `Notification` row at all (see
    `application.moderation_use_cases`'s own docstring... `application.notification_use_cases`'s
    docstring), rather than being recorded and then marked suppressed."""

    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


TERMINAL_DELIVERY_STATUSES = frozenset(
    {DeliveryStatus.SENT, DeliveryStatus.DELIVERED, DeliveryStatus.FAILED}
)


@dataclass(frozen=True)
class RecipientRef:
    """DDD Sec 5.10 VO `RecipientRef` -- an IDENTIFIER only, never an imported `identity.
    UserAccount` object (AIR-01/SAD Sec 8.1: notifications may statically import `shared_kernel,
    configuration` only, not `identity`)."""

    user_id: UUID


@dataclass(frozen=True)
class RenderedContent:
    """DDD Sec 5.10 VO `RenderedContent` (from template [C-ref] + locale) -- frozen at dispatch
    time (Physical DB: "no live template dependency"); a later template edit never mutates an
    already-sent notification's own recorded content."""

    subject: str | None
    body: str
