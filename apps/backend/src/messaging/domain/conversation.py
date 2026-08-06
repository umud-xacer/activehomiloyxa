"""messaging/domain -- the `Conversation` aggregate (DDD Sec 5.7 `AR: Conversation [P]`).
`startConversation` (`contracts/openapi.yaml`) sends its `message` field atomically with creation
-- there is no separate "create an empty conversation" operation -- so `Conversation.start`
always produces a conversation carrying exactly one `Message` and, matching the physical
`purchase_order`-style default (`ck_conversation_status` default `'ACTIVE'`, Physical DB Design),
status `ACTIVE` rather than `INITIATED`. `INITIATED` remains part of the closed status set (both
the OpenAPI schema and the physical CHECK enumerate it) for schema completeness even though no
code path in this task produces it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from messaging.domain.exceptions import (
    BlockedParticipantError,
    IllegalConversationStateTransitionError,
    NotAParticipantError,
    UnknownMessageError,
)
from messaging.domain.message import Message
from messaging.domain.value_objects import ConversationStatus, ListingRef, ParticipantPair
from shared_kernel import UserId


@dataclass(frozen=True)
class Conversation:
    id: UUID
    listing: ListingRef
    participants: ParticipantPair
    status: ConversationStatus
    messages: tuple[Message, ...]
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    lock_version: int = 0

    @staticmethod
    def start(
        *,
        conversation_id: UUID,
        message_id: UUID,
        listing: ListingRef,
        participants: ParticipantPair,
        initial_body: str,
        now: datetime,
        is_blocked: bool,
    ) -> Conversation:
        """I-19's block-enforcement clause, checked here (not merely by the calling use case) --
        `is_blocked` is resolved by the use case from `BlockRepository` *before* this call and
        passed in as a plain fact; the actual refusal decision is made inside the aggregate,
        mirroring `identity.domain.policies.OtpThrottlePolicy`'s and `billing.domain.entitlement.
        EntitlementFactory`'s own "pure domain decision from an externally-resolved fact" shape
        (domain/ itself never performs I/O, Rule 1)."""
        if is_blocked:
            raise BlockedParticipantError
        message = Message.send(
            message_id=message_id,
            conversation_id=conversation_id,
            author_user_id=participants.initiator_user_id,
            body=initial_body,
            now=now,
        )
        return Conversation(
            id=conversation_id,
            listing=listing,
            participants=participants,
            status=ConversationStatus.ACTIVE,
            messages=(message,),
            last_message_at=now,
            created_at=now,
            updated_at=now,
        )

    def send_message(
        self,
        *,
        message_id: UUID,
        author_id: UserId,
        body: str,
        now: datetime,
        is_sender_blocked: bool,
    ) -> Conversation:
        """I-19, both clauses: `NotAParticipantError` if the caller isn't one of the two fixed
        participants; `BlockedParticipantError` (the same domain-side guard as `start`) if the
        recipient has blocked the sender."""
        if not self.participants.contains(author_id):
            raise NotAParticipantError(self.id, author_id.value)
        if is_sender_blocked:
            raise BlockedParticipantError
        message = Message.send(
            message_id=message_id,
            conversation_id=self.id,
            author_user_id=author_id,
            body=body,
            now=now,
        )
        return replace(
            self,
            messages=(*self.messages, message),
            last_message_at=now,
            updated_at=now,
        )

    def mark_message_delivered(self, *, message_id: UUID, now: datetime) -> Conversation:
        for message in self.messages:
            if message.id == message_id:
                updated = tuple(
                    m.mark_delivered(now=now) if m.id == message_id else m for m in self.messages
                )
                return replace(self, messages=updated, updated_at=now)
        raise UnknownMessageError(self.id, message_id)

    def archive(self, *, now: datetime) -> Conversation:
        """Lifecycle-complete but unwired in v1: no OpenAPI operation archives a conversation
        (`contracts/openapi.yaml`'s ten messaging operations have no such endpoint), matching the
        precedent of `billing.domain.order.Order.fulfill`/`Invoice.void` -- implemented and
        domain-tested because the physical/status schema documents the state, flagged in
        `messaging/README.md` "Known gaps" as having no caller."""
        if self.status is not ConversationStatus.ACTIVE:
            raise IllegalConversationStateTransitionError(
                self.id, from_status=self.status.value, to_status=ConversationStatus.ARCHIVED.value
            )
        return replace(self, status=ConversationStatus.ARCHIVED, updated_at=now)
