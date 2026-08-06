"""Shared fixtures for `messaging`'s fast (no-DB) unit + API tests: in-memory fakes for every
port `application/ports.py` declares, mirroring `apps/backend/tests/billing/conftest.py`'s
pattern exactly."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

import pytest

from messaging.domain import Block, Conversation
from shared_kernel import EventEnvelope, UserId


def _encode_cursor(anchor: datetime, row_id: UUID) -> str:
    raw = f"{anchor.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    anchor_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(anchor_str), UUID(row_id)


@dataclass
class FakeConversationRepository:
    """Implements `messaging.application.ports.ConversationRepository`."""

    conversations: dict[UUID, Conversation] = field(default_factory=dict)

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def get_by_listing_and_initiator(
        self, listing_id: UUID, initiator_user_id: UUID
    ) -> Conversation | None:
        for c in self.conversations.values():
            if (
                c.listing.listing_id.value == listing_id
                and c.participants.initiator_user_id.value == initiator_user_id
            ):
                return c
        return None

    async def add(self, conversation: Conversation) -> None:
        self.conversations[conversation.id] = conversation

    async def save(self, conversation: Conversation) -> Conversation:
        self.conversations[conversation.id] = conversation
        return conversation

    async def list_by_participant(
        self, user_id: UUID, *, cursor: str | None, limit: int
    ) -> tuple[list[Conversation], str | None]:
        def _anchor(c: Conversation) -> datetime:
            return c.last_message_at or c.created_at

        items = sorted(
            (
                c
                for c in self.conversations.values()
                if user_id
                in (c.participants.initiator_user_id.value, c.participants.recipient_user_id.value)
            ),
            key=lambda c: (_anchor(c), c.id),
        )
        if cursor is not None:
            anchor, row_id = _decode_cursor(cursor)
            items = [c for c in items if (_anchor(c), c.id) > (anchor, row_id)]
        page = items[: limit + 1]
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = _encode_cursor(_anchor(page[-1]), page[-1].id)
        return page, next_cursor

    async def count_recent_messages_by_author(self, author_id: UUID, *, since: datetime) -> int:
        return sum(
            1
            for c in self.conversations.values()
            for m in c.messages
            if m.author_user_id.value == author_id and m.sent_at >= since
        )


@dataclass
class FakeBlockRepository:
    """Implements `messaging.application.ports.BlockRepository`."""

    blocks: dict[tuple[UUID, UUID], Block] = field(default_factory=dict)

    async def exists(self, *, blocker_user_id: UUID, blocked_user_id: UUID) -> bool:
        return (blocker_user_id, blocked_user_id) in self.blocks

    async def add(self, block: Block) -> None:
        self.blocks[(block.pair.blocker_user_id.value, block.pair.blocked_user_id.value)] = block

    async def delete(self, *, blocker_user_id: UUID, blocked_user_id: UUID) -> None:
        self.blocks.pop((blocker_user_id, blocked_user_id), None)

    async def list_by_blocker(self, blocker_user_id: UUID) -> tuple[Block, ...]:
        return tuple(
            b for (blocker, _blocked), b in self.blocks.items() if blocker == blocker_user_id
        )


class FakeListingOwnerReaderPort:
    """Implements `messaging.application.ports.ListingOwnerReaderPort`."""

    def __init__(self) -> None:
        self.owners: dict[UUID, UserId] = {}

    def seed(self, listing_id: UUID, owner_user_id: UserId) -> None:
        self.owners[listing_id] = owner_user_id

    async def get_owner(self, listing_id: UUID) -> UserId | None:
        return self.owners.get(listing_id)


class FakeContactPolicyPort:
    """Implements `identity.interfaces.ports.ContactPolicyPort` (the slice messaging actually
    calls: `reveal_phone`)."""

    def __init__(self) -> None:
        self.phones: dict[UUID, str] = {}

    def seed(self, user_id: UUID, phone_number: str) -> None:
        self.phones[user_id] = phone_number

    async def get_phone_reveal_mode(
        self, account_id: UserId
    ) -> Literal["ALWAYS", "ON_REQUEST", "NEVER"]:
        return "ALWAYS" if account_id.value in self.phones else "NEVER"

    async def reveal_phone(self, account_id: UserId) -> str | None:
        return self.phones.get(account_id.value)


class FakeRealtimePublisherPort:
    """Implements `messaging.application.ports.RealtimePublisherPort`."""

    def __init__(self) -> None:
        self.published: list[dict[str, object]] = []

    async def publish_message(self, *, recipient_user_id, conversation_id, message) -> None:  # type: ignore[no-untyped-def]
        self.published.append(
            {
                "recipient_user_id": recipient_user_id,
                "conversation_id": conversation_id,
                "message": message,
            }
        )


class FakeMessageSubscriberPort:
    """Implements `messaging.application.ports.MessageSubscriberPort`."""

    def __init__(self, items: list[str] | None = None) -> None:
        self._items = items or []

    async def listen(self, user_id: UUID) -> AsyncIterator[str]:
        for item in self._items:
            yield item


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


@pytest.fixture
def fake_conversations() -> FakeConversationRepository:
    return FakeConversationRepository()


@pytest.fixture
def fake_blocks() -> FakeBlockRepository:
    return FakeBlockRepository()


@pytest.fixture
def fake_listing_owners() -> FakeListingOwnerReaderPort:
    return FakeListingOwnerReaderPort()


@pytest.fixture
def fake_contact_policy() -> FakeContactPolicyPort:
    return FakeContactPolicyPort()


@pytest.fixture
def fake_publisher() -> FakeRealtimePublisherPort:
    return FakeRealtimePublisherPort()


@pytest.fixture
def fake_outbox() -> FakeOutbox:
    return FakeOutbox()
