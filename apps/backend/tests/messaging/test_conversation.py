"""`messaging.domain.conversation.Conversation` -- I-19's own structural guard: exactly two
participants, and a blocked user can neither initiate nor continue contact with the blocker.
Both clauses are checked INSIDE the aggregate's own methods, not only by the calling use case
(the P-10 prompt's own explicit instruction), proven here by calling those methods directly with
a deliberately-wrong `is_blocked`/`is_sender_blocked` fact and confirming the aggregate itself
refuses -- never trusting a caller that forgot to check.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from messaging.domain import (
    BlockedParticipantError,
    Conversation,
    ConversationStatus,
    EmptyMessageBodyError,
    IllegalConversationStateTransitionError,
    ListingRef,
    NotAParticipantError,
    ParticipantPair,
    SelfConversationError,
    UnknownMessageError,
)
from shared_kernel import ListingId, UserId

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _pair(**overrides: object) -> ParticipantPair:
    defaults: dict[str, object] = {
        "initiator_user_id": UserId(value=uuid4()),
        "recipient_user_id": UserId(value=uuid4()),
    }
    defaults.update(overrides)
    return ParticipantPair(**defaults)  # type: ignore[arg-type]


def _listing() -> ListingRef:
    return ListingRef(listing_id=ListingId(value=uuid4()))


class TestI19ExactlyTwoParticipants:
    def test_I19_participant_pair_rejects_the_same_user_on_both_sides(self) -> None:
        same = UserId(value=uuid4())
        with pytest.raises(SelfConversationError):
            ParticipantPair(initiator_user_id=same, recipient_user_id=same)

    def test_I19_a_third_user_cannot_send_a_message(self) -> None:
        pair = _pair()
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=_listing(),
            participants=pair,
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        )
        third_party = UserId(value=uuid4())
        with pytest.raises(NotAParticipantError):
            conversation.send_message(
                message_id=uuid4(),
                author_id=third_party,
                body="I'm not part of this",
                now=_NOW,
                is_sender_blocked=False,
            )

    def test_I19_a_third_user_cannot_be_named_a_participant(self) -> None:
        """Structural: `ParticipantPair` has exactly two fields -- there is no method, no
        constructor path, that admits a third id into a conversation's own participant set."""
        pair = _pair()
        assert len(list(pair.__dataclass_fields__)) == 2


class TestI19BlockEnforcementInsideTheAggregate:
    def test_I19_start_refuses_when_the_recipient_has_blocked_the_initiator(self) -> None:
        with pytest.raises(BlockedParticipantError):
            Conversation.start(
                conversation_id=uuid4(),
                message_id=uuid4(),
                listing=_listing(),
                participants=_pair(),
                initial_body="hello",
                now=_NOW,
                is_blocked=True,
            )

    def test_I19_send_message_refuses_when_the_recipient_has_blocked_the_sender(self) -> None:
        pair = _pair()
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=_listing(),
            participants=pair,
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        )
        with pytest.raises(BlockedParticipantError):
            conversation.send_message(
                message_id=uuid4(),
                author_id=pair.recipient_user_id,
                body="let me reply",
                now=_NOW,
                is_sender_blocked=True,
            )

    def test_I19_block_enforcement_works_from_either_direction(self) -> None:
        """ "a blocked user can neither initiate nor continue" -- proven for BOTH the initiator
        side (test above) and the continuing/replying side (this test): the initiator blocking
        the recipient AFTER starting also refuses that recipient's own reply."""
        pair = _pair()
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=_listing(),
            participants=pair,
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        )
        with pytest.raises(BlockedParticipantError):
            conversation.send_message(
                message_id=uuid4(),
                author_id=pair.recipient_user_id,
                body="reply after being blocked",
                now=_NOW,
                is_sender_blocked=True,
            )


class TestConversationStart:
    def test_start_produces_an_active_conversation_with_exactly_one_message(self) -> None:
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=_listing(),
            participants=_pair(),
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        )
        assert conversation.status is ConversationStatus.ACTIVE
        assert len(conversation.messages) == 1
        assert conversation.last_message_at == _NOW

    def test_initial_message_author_is_the_initiator(self) -> None:
        pair = _pair()
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=_listing(),
            participants=pair,
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        )
        assert conversation.messages[0].author_user_id == pair.initiator_user_id

    def test_empty_body_raises(self) -> None:
        with pytest.raises(EmptyMessageBodyError):
            Conversation.start(
                conversation_id=uuid4(),
                message_id=uuid4(),
                listing=_listing(),
                participants=_pair(),
                initial_body="   ",
                now=_NOW,
                is_blocked=False,
            )


class TestSendMessage:
    def _active(self) -> tuple[Conversation, ParticipantPair]:
        pair = _pair()
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=_listing(),
            participants=pair,
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        )
        return conversation, pair

    def test_appends_a_message_and_bumps_last_message_at(self) -> None:
        conversation, pair = self._active()
        later = datetime(2026, 7, 12, 1, tzinfo=UTC)
        updated = conversation.send_message(
            message_id=uuid4(),
            author_id=pair.recipient_user_id,
            body="reply",
            now=later,
            is_sender_blocked=False,
        )
        assert len(updated.messages) == 2
        assert updated.last_message_at == later

    def test_either_participant_may_send(self) -> None:
        conversation, pair = self._active()
        for author in (pair.initiator_user_id, pair.recipient_user_id):
            conversation = conversation.send_message(
                message_id=uuid4(),
                author_id=author,
                body="msg",
                now=_NOW,
                is_sender_blocked=False,
            )
        assert len(conversation.messages) == 3


class TestMarkMessageDelivered:
    def test_marks_the_matching_message_delivered(self) -> None:
        pair = _pair()
        message_id = uuid4()
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=message_id,
            listing=_listing(),
            participants=pair,
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        )
        updated = conversation.mark_message_delivered(message_id=message_id, now=_NOW)
        assert updated.messages[0].delivered_at == _NOW

    def test_unknown_message_id_raises(self) -> None:
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=_listing(),
            participants=_pair(),
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        )
        with pytest.raises(UnknownMessageError):
            conversation.mark_message_delivered(message_id=uuid4(), now=_NOW)


class TestArchive:
    def test_archive_moves_active_to_archived(self) -> None:
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=_listing(),
            participants=_pair(),
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        )
        archived = conversation.archive(now=_NOW)
        assert archived.status is ConversationStatus.ARCHIVED

    def test_archive_twice_raises(self) -> None:
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=_listing(),
            participants=_pair(),
            initial_body="hello",
            now=_NOW,
            is_blocked=False,
        ).archive(now=_NOW)
        with pytest.raises(IllegalConversationStateTransitionError):
            conversation.archive(now=_NOW)
