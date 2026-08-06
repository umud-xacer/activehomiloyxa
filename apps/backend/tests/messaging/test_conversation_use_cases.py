"""`messaging.application.conversation_use_cases.ConversationUseCases`."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from messaging.application.conversation_use_cases import ConversationUseCases
from messaging.application.exceptions import (
    ConversationAlreadyExistsError,
    ConversationNotFoundError,
    ListingOwnerUnknownError,
)
from messaging.domain import (
    MESSAGE_RATE_LIMIT_MAX_PER_WINDOW,
    Block,
    BlockedParticipantError,
    Conversation,
    NotAParticipantError,
    RateLimitExceededError,
)
from shared_kernel import UserId

from .conftest import (
    FakeBlockRepository,
    FakeContactPolicyPort,
    FakeConversationRepository,
    FakeListingOwnerReaderPort,
    FakeOutbox,
    FakeRealtimePublisherPort,
)

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.fixture
def use_cases(
    fake_conversations: FakeConversationRepository,
    fake_blocks: FakeBlockRepository,
    fake_listing_owners: FakeListingOwnerReaderPort,
    fake_publisher: FakeRealtimePublisherPort,
    fake_contact_policy: FakeContactPolicyPort,
    fake_outbox: FakeOutbox,
) -> ConversationUseCases:
    return ConversationUseCases(
        conversations=fake_conversations,
        blocks=fake_blocks,
        listing_owners=fake_listing_owners,
        publisher=fake_publisher,
        contact_policy=fake_contact_policy,
        outbox=fake_outbox,
    )


class TestStartConversation:
    async def test_resolves_recipient_from_the_listing_owner_projection(
        self,
        use_cases: ConversationUseCases,
        fake_listing_owners: FakeListingOwnerReaderPort,
        fake_outbox: FakeOutbox,
        fake_publisher: FakeRealtimePublisherPort,
    ) -> None:
        listing_id = uuid4()
        owner = UserId(value=uuid4())
        fake_listing_owners.seed(listing_id, owner)
        initiator = UserId(value=uuid4())

        conversation = await use_cases.start_conversation(
            initiator_user_id=initiator, listing_id=listing_id, message_body="hi", now=_NOW
        )
        assert conversation.participants.recipient_user_id == owner
        assert [e.event_type for e in fake_outbox.events] == ["ChatInitiated", "MessageSent"]
        assert len(fake_publisher.published) == 1
        assert fake_publisher.published[0]["recipient_user_id"] == owner.value

    async def test_raises_listing_owner_unknown_when_projection_is_empty(
        self, use_cases: ConversationUseCases
    ) -> None:
        with pytest.raises(ListingOwnerUnknownError):
            await use_cases.start_conversation(
                initiator_user_id=UserId(value=uuid4()),
                listing_id=uuid4(),
                message_body="hi",
                now=_NOW,
            )

    async def test_raises_already_exists_for_a_second_conversation_same_listing_and_initiator(
        self,
        use_cases: ConversationUseCases,
        fake_listing_owners: FakeListingOwnerReaderPort,
    ) -> None:
        listing_id = uuid4()
        fake_listing_owners.seed(listing_id, UserId(value=uuid4()))
        initiator = UserId(value=uuid4())
        await use_cases.start_conversation(
            initiator_user_id=initiator, listing_id=listing_id, message_body="hi", now=_NOW
        )
        with pytest.raises(ConversationAlreadyExistsError):
            await use_cases.start_conversation(
                initiator_user_id=initiator,
                listing_id=listing_id,
                message_body="hi again",
                now=_NOW,
            )

    async def test_I19_raises_when_the_owner_has_blocked_the_initiator(
        self,
        use_cases: ConversationUseCases,
        fake_listing_owners: FakeListingOwnerReaderPort,
        fake_blocks: FakeBlockRepository,
    ) -> None:
        listing_id = uuid4()
        owner = UserId(value=uuid4())
        initiator = UserId(value=uuid4())
        fake_listing_owners.seed(listing_id, owner)
        await fake_blocks.add(
            Block.create(
                block_id=uuid4(), blocker_user_id=owner, blocked_user_id=initiator, now=_NOW
            )
        )
        with pytest.raises(BlockedParticipantError):
            await use_cases.start_conversation(
                initiator_user_id=initiator, listing_id=listing_id, message_body="hi", now=_NOW
            )

    async def test_rate_limit_exceeded_raises(
        self,
        use_cases: ConversationUseCases,
        fake_listing_owners: FakeListingOwnerReaderPort,
        fake_conversations: FakeConversationRepository,
    ) -> None:
        initiator = UserId(value=uuid4())
        # seed enough recent messages under a DIFFERENT listing/conversation to trip the
        # per-user (not per-conversation) rate limit.
        owner = UserId(value=uuid4())
        seeded_listing = uuid4()
        fake_listing_owners.seed(seeded_listing, owner)
        seeded = await use_cases.start_conversation(
            initiator_user_id=initiator, listing_id=seeded_listing, message_body="seed", now=_NOW
        )
        for _ in range(MESSAGE_RATE_LIMIT_MAX_PER_WINDOW - 1):
            seeded = await use_cases.send_message(
                seeded.id, author_id=initiator, body="x", now=_NOW
            )

        new_listing = uuid4()
        fake_listing_owners.seed(new_listing, UserId(value=uuid4()))
        with pytest.raises(RateLimitExceededError):
            await use_cases.start_conversation(
                initiator_user_id=initiator, listing_id=new_listing, message_body="hi", now=_NOW
            )


class TestSendMessage:
    async def _seeded(
        self,
        use_cases: ConversationUseCases,
        fake_listing_owners: FakeListingOwnerReaderPort,
    ) -> tuple[UserId, UserId, Conversation]:
        listing_id = uuid4()
        owner = UserId(value=uuid4())
        initiator = UserId(value=uuid4())
        fake_listing_owners.seed(listing_id, owner)
        conversation = await use_cases.start_conversation(
            initiator_user_id=initiator, listing_id=listing_id, message_body="hi", now=_NOW
        )
        return initiator, owner, conversation

    async def test_recipient_may_reply(
        self, use_cases: ConversationUseCases, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        _initiator, owner, conversation = await self._seeded(use_cases, fake_listing_owners)
        updated = await use_cases.send_message(
            conversation.id, author_id=owner, body="reply", now=_NOW
        )
        assert len(updated.messages) == 2

    async def test_I19_non_participant_cannot_send(
        self, use_cases: ConversationUseCases, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        _initiator, _owner, conversation = await self._seeded(use_cases, fake_listing_owners)
        with pytest.raises(NotAParticipantError):
            await use_cases.send_message(
                conversation.id, author_id=UserId(value=uuid4()), body="intruder", now=_NOW
            )

    async def test_unknown_conversation_raises_not_found(
        self, use_cases: ConversationUseCases
    ) -> None:
        with pytest.raises(ConversationNotFoundError):
            await use_cases.send_message(
                uuid4(), author_id=UserId(value=uuid4()), body="x", now=_NOW
            )


class TestGetConversationAndListMessages:
    async def test_I19_non_participant_cannot_read(
        self, use_cases: ConversationUseCases, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        listing_id = uuid4()
        fake_listing_owners.seed(listing_id, UserId(value=uuid4()))
        conversation = await use_cases.start_conversation(
            initiator_user_id=UserId(value=uuid4()),
            listing_id=listing_id,
            message_body="hi",
            now=_NOW,
        )
        with pytest.raises(NotAParticipantError):
            await use_cases.get_conversation(conversation.id, user_id=UserId(value=uuid4()))
        with pytest.raises(NotAParticipantError):
            await use_cases.list_messages(
                conversation.id, user_id=UserId(value=uuid4()), cursor=None, limit=20
            )

    async def test_participant_can_read(
        self, use_cases: ConversationUseCases, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        listing_id = uuid4()
        initiator = UserId(value=uuid4())
        fake_listing_owners.seed(listing_id, UserId(value=uuid4()))
        conversation = await use_cases.start_conversation(
            initiator_user_id=initiator, listing_id=listing_id, message_body="hi", now=_NOW
        )
        fetched = await use_cases.get_conversation(conversation.id, user_id=initiator)
        assert fetched.id == conversation.id


class TestRevealPhone:
    async def test_returns_the_number_when_the_counterpart_allows(
        self,
        use_cases: ConversationUseCases,
        fake_listing_owners: FakeListingOwnerReaderPort,
        fake_contact_policy: FakeContactPolicyPort,
        fake_outbox: FakeOutbox,
    ) -> None:
        listing_id = uuid4()
        owner = UserId(value=uuid4())
        initiator = UserId(value=uuid4())
        fake_listing_owners.seed(listing_id, owner)
        fake_contact_policy.seed(owner.value, "+998901234567")
        conversation = await use_cases.start_conversation(
            initiator_user_id=initiator, listing_id=listing_id, message_body="hi", now=_NOW
        )

        phone = await use_cases.reveal_phone(conversation.id, requester_id=initiator, now=_NOW)
        assert phone == "+998901234567"
        assert "PhoneRevealed" in [e.event_type for e in fake_outbox.events]

    async def test_returns_none_when_the_counterpart_declines(
        self,
        use_cases: ConversationUseCases,
        fake_listing_owners: FakeListingOwnerReaderPort,
        fake_outbox: FakeOutbox,
    ) -> None:
        listing_id = uuid4()
        owner = UserId(value=uuid4())
        initiator = UserId(value=uuid4())
        fake_listing_owners.seed(listing_id, owner)
        conversation = await use_cases.start_conversation(
            initiator_user_id=initiator, listing_id=listing_id, message_body="hi", now=_NOW
        )

        phone = await use_cases.reveal_phone(conversation.id, requester_id=initiator, now=_NOW)
        assert phone is None
        assert "PhoneRevealed" not in [e.event_type for e in fake_outbox.events]

    async def test_I19_non_participant_cannot_reveal(
        self, use_cases: ConversationUseCases, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        listing_id = uuid4()
        fake_listing_owners.seed(listing_id, UserId(value=uuid4()))
        conversation = await use_cases.start_conversation(
            initiator_user_id=UserId(value=uuid4()),
            listing_id=listing_id,
            message_body="hi",
            now=_NOW,
        )
        with pytest.raises(NotAParticipantError):
            await use_cases.reveal_phone(
                conversation.id, requester_id=UserId(value=uuid4()), now=_NOW
            )


class TestMarkMessageDelivered:
    async def test_marks_the_message_delivered(
        self, use_cases: ConversationUseCases, fake_listing_owners: FakeListingOwnerReaderPort
    ) -> None:
        listing_id = uuid4()
        fake_listing_owners.seed(listing_id, UserId(value=uuid4()))
        conversation = await use_cases.start_conversation(
            initiator_user_id=UserId(value=uuid4()),
            listing_id=listing_id,
            message_body="hi",
            now=_NOW,
        )
        message_id = conversation.messages[0].id
        updated = await use_cases.mark_message_delivered(conversation.id, message_id, now=_NOW)
        assert updated.messages[0].delivered_at == _NOW
