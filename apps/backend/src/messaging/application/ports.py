"""messaging/application -- ports (repositories, the realtime fan-out publisher). Re-exports
`identity.interfaces.ports.ContactPolicyPort` rather than reinventing an identical Protocol:
SAD Sec 8.1's static import matrix permits `messaging -> identity` (interfaces/ only, AIR-02),
and `ContactPolicyPort`'s own docstring names messaging as its intended, purpose-built consumer
("consulted in-process by messaging (privacy-gated phone reveal)") -- unlike catalog/billing,
which chose self-imposed restraint even though SAD permits `-> identity` for them too, this
module's own FR-MSG-003 IS the reason that port exists. Only `shared_kernel` primitives and
`identity.interfaces` Protocol types cross this boundary, never `identity.domain`/
`identity.infrastructure` (AIR-02)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol
from uuid import UUID

from identity.interfaces.ports import ContactPolicyPort
from messaging.domain import Block, Conversation, Message
from shared_kernel import UserId

__all__ = [
    "BlockRepository",
    "ContactPolicyPort",
    "ConversationRepository",
    "ListingOwnerReaderPort",
    "MessageSubscriberPort",
    "RealtimePublisherPort",
]


class ConversationRepository(Protocol):
    async def get_by_id(self, conversation_id: UUID) -> Conversation | None: ...

    async def get_by_listing_and_initiator(
        self, listing_id: UUID, initiator_user_id: UUID
    ) -> Conversation | None:
        """Backs the Physical DB `UNIQUE(listing_id, initiator_user_id)` conflict check."""
        ...

    async def add(self, conversation: Conversation) -> None: ...

    async def save(self, conversation: Conversation) -> Conversation: ...

    async def list_by_participant(
        self, user_id: UUID, *, cursor: str | None, limit: int
    ) -> tuple[list[Conversation], str | None]:
        """Either side of `ParticipantPair` -- a user's own inbox (`listConversations`)."""
        ...

    async def count_recent_messages_by_author(self, author_id: UUID, *, since: datetime) -> int:
        """BR-MSG-03's own per-user count, across every conversation `author_id` has sent into
        (not scoped to one conversation) -- backs `MessageRateLimitPolicy`."""
        ...


class BlockRepository(Protocol):
    async def exists(self, *, blocker_user_id: UUID, blocked_user_id: UUID) -> bool: ...

    async def add(self, block: Block) -> None: ...

    async def delete(self, *, blocker_user_id: UUID, blocked_user_id: UUID) -> None:
        """Physical `DELETE` (Physical DB Design: "physical DELETE on unblock permitted") --
        idempotent, a no-op if the pair was never blocked."""
        ...

    async def list_by_blocker(self, blocker_user_id: UUID) -> tuple[Block, ...]: ...


class ListingOwnerReaderPort(Protocol):
    """Backs `startConversation`'s server-side recipient resolution (`ConversationCreateRequest`
    carries `listingId` + `message` only, no recipient -- OpenAPI deliberately does not let the
    caller assert who the recipient is). Reads messaging's own locally projected `listing_owner_
    projection` table (`infrastructure.event_projection.handle_listing_created`), never a live
    call into `catalog` (forbidden, AIR-10)."""

    async def get_owner(self, listing_id: UUID) -> UserId | None:
        """`None` if the projection has not yet observed this listing's `ListingCreated` event
        (fresh-enough listings, or a genuinely unknown id) -- the calling use case maps this to
        `ListingOwnerUnknownError` (503), never guesses a recipient."""
        ...


class RealtimePublisherPort(Protocol):
    """The Redis pub/sub fan-out bus (DEC-11, SAD Sec 6) -- Redis is a bus, never the source of
    truth; the message is already durably persisted (`ConversationRepository.save`) before this
    is ever called."""

    async def publish_message(
        self, *, recipient_user_id: UUID, conversation_id: UUID, message: Message
    ) -> None: ...


class MessageSubscriberPort(Protocol):
    """The realtime gateway's own read side of the same Redis pub/sub bus -- never used by the
    stateless HTTP tier (`interfaces/routers.py` never depends on this port)."""

    def listen(self, user_id: UUID) -> AsyncIterator[str]: ...
