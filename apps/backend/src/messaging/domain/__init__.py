"""messaging/domain -- the `Conversation` (with `Message` children) and `Block` aggregates
(DDD Sec 5.7), value objects, and invariant-guarding exceptions. See `messaging/README.md`."""

from __future__ import annotations

from messaging.domain.block import Block
from messaging.domain.conversation import Conversation
from messaging.domain.exceptions import (
    BlockedParticipantError,
    EmptyMessageBodyError,
    IllegalConversationStateTransitionError,
    MessagingDomainError,
    NotAParticipantError,
    RateLimitExceededError,
    SelfBlockError,
    SelfConversationError,
    UnknownMessageError,
)
from messaging.domain.message import Message
from messaging.domain.policies import (
    MESSAGE_RATE_LIMIT_MAX_PER_WINDOW,
    MESSAGE_RATE_LIMIT_WINDOW_SECONDS,
    MessageRateLimitPolicy,
)
from messaging.domain.value_objects import (
    BlockPair,
    ConversationStatus,
    ListingRef,
    ParticipantPair,
)

__all__ = [
    "MESSAGE_RATE_LIMIT_MAX_PER_WINDOW",
    "MESSAGE_RATE_LIMIT_WINDOW_SECONDS",
    "Block",
    "BlockPair",
    "BlockedParticipantError",
    "Conversation",
    "ConversationStatus",
    "EmptyMessageBodyError",
    "IllegalConversationStateTransitionError",
    "ListingRef",
    "Message",
    "MessageRateLimitPolicy",
    "MessagingDomainError",
    "NotAParticipantError",
    "ParticipantPair",
    "RateLimitExceededError",
    "SelfBlockError",
    "SelfConversationError",
    "UnknownMessageError",
]
