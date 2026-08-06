"""messaging/domain -- the `Message` child entity (DDD Sec 5.7: "Entities: Message (author,
body, timestamp, delivery status)"). Persists inside the `Conversation` cluster -- no repository
of its own (Logical Sec 18.2), never constructed or mutated except through a `Conversation`
method.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from messaging.domain.exceptions import EmptyMessageBodyError
from shared_kernel import UserId


@dataclass(frozen=True)
class Message:
    id: UUID
    conversation_id: UUID
    author_user_id: UserId
    body: str
    sent_at: datetime
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    """No v1 code path ever sets this -- no `markMessageRead` operation and no read-receipt wire
    protocol exists in `contracts/openapi.yaml` or the Domain Model's messaging events. The
    physical column exists (Physical DB Design) and is modelled here for a complete read path,
    but stays permanently `None` in v1 (flagged in `messaging/README.md` "Known gaps" rather than
    inventing an unspecified mark-read mechanism)."""

    @staticmethod
    def send(
        *, message_id: UUID, conversation_id: UUID, author_user_id: UserId, body: str, now: datetime
    ) -> Message:
        if not body.strip():
            raise EmptyMessageBodyError
        return Message(
            id=message_id,
            conversation_id=conversation_id,
            author_user_id=author_user_id,
            body=body,
            sent_at=now,
        )

    def mark_delivered(self, *, now: datetime) -> Message:
        """Set by the realtime gateway once it has actually pushed this message down an active,
        authenticated WebSocket connection (FR-MSG-002: "deliver ... in real time") -- a message
        that was only persisted, with no connected recipient at send time, stays `delivered_at IS
        NULL` (Physical DB's own "the only mutable columns" note) until the recipient reconnects
        and the gateway redelivers it. Idempotent: redelivery does not overwrite an earlier
        timestamp."""
        if self.delivered_at is not None:
            return self
        return replace(self, delivered_at=now)
