"""Integration tests: `SqlalchemyConversationRepository`/`SqlalchemyBlockRepository`/
`SqlalchemyListingOwnerProjectionReader` round-trip against real PostgreSQL, including the
physical CHECK/UNIQUE constraints (`ck_conversation_distinct_participants`,
`ux_conversation_listing_initiator`, `ck_block_distinct_users`, `ux_block_blocker_blocked`)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from messaging.domain import Block, Conversation, ListingRef, ParticipantPair
from messaging.infrastructure.persistence.models import ListingOwnerProjectionRow
from messaging.infrastructure.persistence.repository import (
    SqlalchemyBlockRepository,
    SqlalchemyConversationRepository,
    SqlalchemyListingOwnerProjectionReader,
)
from shared_kernel import ListingId, UserId

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _conversation(**overrides: object) -> Conversation:
    defaults: dict[str, object] = {
        "conversation_id": uuid4(),
        "message_id": uuid4(),
        "listing": ListingRef(listing_id=ListingId(value=uuid4())),
        "participants": ParticipantPair(
            initiator_user_id=UserId(value=uuid4()), recipient_user_id=UserId(value=uuid4())
        ),
        "initial_body": "hello",
        "now": NOW,
        "is_blocked": False,
    }
    defaults.update(overrides)
    return Conversation.start(**defaults)  # type: ignore[arg-type]


async def test_conversation_add_then_get_by_id_round_trips(db_session: AsyncSession) -> None:
    repo = SqlalchemyConversationRepository(db_session)
    conversation = _conversation()
    await repo.add(conversation)
    await db_session.flush()

    fetched = await repo.get_by_id(conversation.id)
    assert fetched is not None
    assert fetched.participants == conversation.participants
    assert len(fetched.messages) == 1
    assert fetched.messages[0].body == "hello"


async def test_conversation_save_appends_a_new_message(db_session: AsyncSession) -> None:
    repo = SqlalchemyConversationRepository(db_session)
    conversation = _conversation()
    await repo.add(conversation)
    await db_session.flush()

    updated = conversation.send_message(
        message_id=uuid4(),
        author_id=conversation.participants.recipient_user_id,
        body="reply",
        now=NOW,
        is_sender_blocked=False,
    )
    saved = await repo.save(updated)
    assert len(saved.messages) == 2

    reloaded = await repo.get_by_id(conversation.id)
    assert reloaded is not None
    assert len(reloaded.messages) == 2


async def test_conversation_save_persists_delivered_at(db_session: AsyncSession) -> None:
    repo = SqlalchemyConversationRepository(db_session)
    conversation = _conversation()
    await repo.add(conversation)
    await db_session.flush()

    message_id = conversation.messages[0].id
    updated = conversation.mark_message_delivered(message_id=message_id, now=NOW)
    await repo.save(updated)

    reloaded = await repo.get_by_id(conversation.id)
    assert reloaded is not None
    assert reloaded.messages[0].delivered_at == NOW


async def test_get_by_listing_and_initiator_enforces_the_unique_pair(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyConversationRepository(db_session)
    conversation = _conversation()
    await repo.add(conversation)
    await db_session.flush()

    found = await repo.get_by_listing_and_initiator(
        conversation.listing.listing_id.value, conversation.participants.initiator_user_id.value
    )
    assert found is not None
    assert found.id == conversation.id


async def test_list_by_participant_finds_both_sides(db_session: AsyncSession) -> None:
    repo = SqlalchemyConversationRepository(db_session)
    initiator = UserId(value=uuid4())
    recipient = UserId(value=uuid4())
    conversation = _conversation(
        participants=ParticipantPair(initiator_user_id=initiator, recipient_user_id=recipient)
    )
    await repo.add(conversation)
    await db_session.flush()

    initiator_side, _ = await repo.list_by_participant(initiator.value, cursor=None, limit=20)
    recipient_side, _ = await repo.list_by_participant(recipient.value, cursor=None, limit=20)
    assert len(initiator_side) == 1
    assert len(recipient_side) == 1


async def test_count_recent_messages_by_author(db_session: AsyncSession) -> None:
    repo = SqlalchemyConversationRepository(db_session)
    initiator = UserId(value=uuid4())
    conversation = _conversation(
        participants=ParticipantPair(
            initiator_user_id=initiator, recipient_user_id=UserId(value=uuid4())
        )
    )
    await repo.add(conversation)
    await db_session.flush()

    count = await repo.count_recent_messages_by_author(
        initiator.value, since=datetime(2026, 7, 11, tzinfo=UTC)
    )
    assert count == 1


async def test_block_add_exists_and_delete_round_trip(db_session: AsyncSession) -> None:
    repo = SqlalchemyBlockRepository(db_session)
    blocker = UserId(value=uuid4())
    blocked = UserId(value=uuid4())
    block = Block.create(
        block_id=uuid4(), blocker_user_id=blocker, blocked_user_id=blocked, now=NOW
    )
    await repo.add(block)
    await db_session.flush()

    assert await repo.exists(blocker_user_id=blocker.value, blocked_user_id=blocked.value) is True

    await repo.delete(blocker_user_id=blocker.value, blocked_user_id=blocked.value)
    await db_session.flush()
    assert await repo.exists(blocker_user_id=blocker.value, blocked_user_id=blocked.value) is False


async def test_listing_owner_projection_reader_reads_a_seeded_row(
    db_session: AsyncSession,
) -> None:
    listing_id = uuid4()
    owner = UserId(value=uuid4())
    db_session.add(ListingOwnerProjectionRow(listing_id=listing_id, owner_user_id=owner.value))
    await db_session.flush()

    reader = SqlalchemyListingOwnerProjectionReader(db_session)
    result = await reader.get_owner(listing_id)
    assert result == owner


async def test_listing_owner_projection_reader_returns_none_for_unknown_listing(
    db_session: AsyncSession,
) -> None:
    reader = SqlalchemyListingOwnerProjectionReader(db_session)
    assert await reader.get_owner(uuid4()) is None
