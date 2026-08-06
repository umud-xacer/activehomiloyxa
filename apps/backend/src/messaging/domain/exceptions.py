"""messaging/domain -- typed exceptions, one per invariant (Standing Orders Rule 10)."""

from __future__ import annotations

from uuid import UUID


class MessagingDomainError(Exception):
    """Base for every typed exception raised by messaging's domain/ layer."""


class SelfConversationError(MessagingDomainError):
    """A `ParticipantPair`'s two sides must be different users (Physical DB `ck_conversation_...`
    matching `initiator_user_id <> recipient_user_id`)."""

    def __init__(self) -> None:
        super().__init__("a conversation cannot have the same user as both participants")


class SelfBlockError(MessagingDomainError):
    """A `Block`'s blocker and blocked side must be different users (Physical DB
    `ck_block_...` matching `blocker_user_id <> blocked_user_id`)."""

    def __init__(self) -> None:
        super().__init__("a user cannot block themselves")


class NotAParticipantError(MessagingDomainError):
    """I-19: only the conversation's own two participants may read or write it -- a third user
    is refused by the aggregate itself, not only by an API-layer ownership check."""

    def __init__(self, conversation_id: UUID, user_id: UUID) -> None:
        self.conversation_id = conversation_id
        self.user_id = user_id
        super().__init__(f"user {user_id} is not a participant of conversation {conversation_id}")


class BlockedParticipantError(MessagingDomainError):
    """I-19: "a blocked user can neither initiate nor continue contact with the blocker." The
    calling use case resolves the block fact (via `BlockRepository`) and passes it in; this is
    the domain-side guard that actually refuses the action -- mirrors `identity.domain.policies.
    OtpThrottlePolicy`'s and `billing.domain.entitlement.EntitlementFactory`'s own pattern of a
    pure domain decision made from an externally-resolved fact, never an I/O call inside
    domain/."""

    def __init__(self) -> None:
        super().__init__("the recipient has blocked the sender; message refused")


class EmptyMessageBodyError(MessagingDomainError):
    def __init__(self) -> None:
        super().__init__("a message body must not be empty")


class RateLimitExceededError(MessagingDomainError):
    """BR-MSG-03: per-user messaging rate limit, on both conversation initiation and message
    send. `retry_after_seconds` matches the `Retry-After`/`X-RateLimit-*` headers Security Sec
    3.1 requires on every 429 response, regardless of which of the three enforcement points
    (edge/OTP/messaging) produced it."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"messaging rate limit exceeded; retry after {retry_after_seconds}s")


class IllegalConversationStateTransitionError(MessagingDomainError):
    def __init__(self, conversation_id: UUID, *, from_status: str, to_status: str) -> None:
        self.conversation_id = conversation_id
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"conversation {conversation_id} cannot transition {from_status} -> {to_status}"
        )


class UnknownMessageError(MessagingDomainError):
    """`Conversation.mark_message_delivered` was called with a `message_id` that is not one of
    this conversation's own children -- a data-consistency bug, never a user-facing 404 (the
    only caller is the realtime gateway acting on its own just-published payload)."""

    def __init__(self, conversation_id: UUID, message_id: UUID) -> None:
        self.conversation_id = conversation_id
        self.message_id = message_id
        super().__init__(f"conversation {conversation_id} has no message {message_id}")
