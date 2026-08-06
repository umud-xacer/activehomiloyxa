"""messaging (BC-07) domain events -- DDD Sec 6, the authoritative v1 event catalogue.

STATUS: frozen (Task P-01). Schema only: each class is the shared envelope
(`shared_kernel.EventEnvelope`) with `event_type` pinned to its own past-tense name. No
publishing logic, no handlers -- that is outbox/adapter work for a later task. Do not add an
event here that is not a row in DDD Sec 6 for this context; do not remove one either without an
ADR (Playbook Sec 18) amending the Domain Model.
"""

from __future__ import annotations

from typing import Literal

from shared_kernel import EventEnvelope


class ChatInitiated(EventEnvelope):
    """Emitted when: First message on a listing.

    Principal consumers: Analytics, Notifications.
    """

    event_type: Literal["ChatInitiated"] = "ChatInitiated"


class MessageSent(EventEnvelope):
    """Emitted when: Message delivered.

    Principal consumers: Notifications (offline recipient).
    """

    event_type: Literal["MessageSent"] = "MessageSent"


class UserBlocked(EventEnvelope):
    """Emitted when: Block created.

    Principal consumers: -- (internal).
    """

    event_type: Literal["UserBlocked"] = "UserBlocked"


class PhoneRevealed(EventEnvelope):
    """Emitted when: Permitted reveal.

    Principal consumers: Analytics.
    """

    event_type: Literal["PhoneRevealed"] = "PhoneRevealed"


class ContentReported(EventEnvelope):
    """Emitted when: User report on listing/conversation/user (BC-07 / BC-03 -- jointly sourced from Messaging and Catalog).

    Principal consumers: Moderation.
    """

    event_type: Literal["ContentReported"] = "ContentReported"
