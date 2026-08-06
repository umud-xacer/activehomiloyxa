"""messaging/domain -- value objects (DDD Sec 5.7)."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from messaging.domain.exceptions import SelfBlockError, SelfConversationError
from shared_kernel import ListingId, UserId


class ConversationStatus(enum.StrEnum):
    """Physical DB `ck_conversation_status` (Logical Data Model Sec 3.7: "Initiated -> Active ->
    Archived"). `INITIATED` is retained in the closed set even though `Conversation.start`
    always produces `ACTIVE` in v1 (the atomic first-message design, see `conversation.py`'s own
    module docstring) -- OpenAPI's own `Conversation.status` enum and the physical CHECK both
    still enumerate all three."""

    INITIATED = "INITIATED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class ListingRef:
    """The listing a conversation is scoped to, referenced by identifier only (SAD Sec 8.1:
    messaging may import `shared_kernel` + `identity` only -- never `catalog`)."""

    listing_id: ListingId


@dataclass(frozen=True)
class ParticipantPair:
    """Exactly two participants (I-19): the user who started the conversation and the listing's
    owner on the other side. Order matters for `UNIQUE(listing_id, initiator_user_id)` (Physical
    DB) -- `initiator_user_id`/`recipient_user_id` are fixed roles, not an unordered set."""

    initiator_user_id: UserId
    recipient_user_id: UserId

    def __post_init__(self) -> None:
        if self.initiator_user_id == self.recipient_user_id:
            raise SelfConversationError

    def contains(self, user_id: UserId) -> bool:
        return user_id in (self.initiator_user_id, self.recipient_user_id)

    def other(self, user_id: UserId) -> UserId:
        """The counterparty of `user_id` within this pair. Caller must have already confirmed
        `contains(user_id)` -- returns the initiator if `user_id` is not the initiator, which is
        only meaningful when `user_id` actually IS a participant."""
        return (
            self.recipient_user_id if user_id == self.initiator_user_id else self.initiator_user_id
        )


@dataclass(frozen=True)
class BlockPair:
    """`Block`'s own ordered pair (Physical DB `UNIQUE(blocker_user_id, blocked_user_id)`) --
    directed, unlike `ParticipantPair`: A blocking B does not imply B blocks A."""

    blocker_user_id: UserId
    blocked_user_id: UserId

    def __post_init__(self) -> None:
        if self.blocker_user_id == self.blocked_user_id:
            raise SelfBlockError
