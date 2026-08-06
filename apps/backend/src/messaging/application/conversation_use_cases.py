"""messaging/application -- `ConversationUseCases`: `startConversation`, `listConversations`,
`getConversation`, `listMessages`, `sendMessage`, `revealPhone`, plus `mark_message_delivered`
(called only by the realtime gateway, no REST operation of its own). Shared verbatim by BOTH
runtimes (the stateless HTTP tier's routers and the separate realtime gateway, DEC-11) -- neither
duplicates this module's business logic, only this file's own methods are ever called.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from contracts.events.messaging import ChatInitiated, MessageSent, PhoneRevealed
from messaging.application.exceptions import (
    ConversationAlreadyExistsError,
    ConversationNotFoundError,
    ListingOwnerUnknownError,
)
from messaging.application.ports import (
    BlockRepository,
    ContactPolicyPort,
    ConversationRepository,
    ListingOwnerReaderPort,
    RealtimePublisherPort,
)
from messaging.domain import (
    MESSAGE_RATE_LIMIT_WINDOW_SECONDS,
    Conversation,
    ListingRef,
    Message,
    MessageRateLimitPolicy,
    NotAParticipantError,
    ParticipantPair,
)
from shared_kernel import ListingId, OutboxPort, UserId


class ConversationUseCases:
    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        blocks: BlockRepository,
        listing_owners: ListingOwnerReaderPort,
        publisher: RealtimePublisherPort,
        contact_policy: ContactPolicyPort,
        outbox: OutboxPort,
    ) -> None:
        self._conversations = conversations
        self._blocks = blocks
        self._listing_owners = listing_owners
        self._publisher = publisher
        self._contact_policy = contact_policy
        self._outbox = outbox

    async def start_conversation(
        self,
        *,
        initiator_user_id: UserId,
        listing_id: UUID,
        message_body: str,
        now: datetime,
    ) -> Conversation:
        """`recipient_user_id` is never caller-supplied (`ConversationCreateRequest` has no such
        field, deliberately -- a client-asserted recipient would let a caller message an
        arbitrary user under someone else's real `listingId`); it is resolved server-side from
        `listing_id` via `ListingOwnerReaderPort`."""
        existing = await self._conversations.get_by_listing_and_initiator(
            listing_id, initiator_user_id.value
        )
        if existing is not None:
            raise ConversationAlreadyExistsError(existing.id)

        owner_id = await self._listing_owners.get_owner(listing_id)
        if owner_id is None:
            raise ListingOwnerUnknownError(listing_id)
        recipient_user_id = owner_id

        recent_count = await self._conversations.count_recent_messages_by_author(
            initiator_user_id.value, since=_rate_limit_window_start(now)
        )
        MessageRateLimitPolicy().check(recent_message_count=recent_count)

        is_blocked = await self._blocks.exists(
            blocker_user_id=recipient_user_id.value, blocked_user_id=initiator_user_id.value
        )
        conversation = Conversation.start(
            conversation_id=uuid4(),
            message_id=uuid4(),
            listing=ListingRef(listing_id=ListingId(value=listing_id)),
            participants=ParticipantPair(
                initiator_user_id=initiator_user_id, recipient_user_id=recipient_user_id
            ),
            initial_body=message_body,
            now=now,
            is_blocked=is_blocked,
        )
        await self._conversations.add(conversation)

        first_message = conversation.messages[0]
        await self._outbox.append(
            ChatInitiated(
                event_id=uuid4(),
                occurred_at=now,
                actor=initiator_user_id.value,
                aggregate_type="Conversation",
                aggregate_id=conversation.id,
                payload=_chat_initiated_payload(conversation),
            )
        )
        await self._outbox.append(
            MessageSent(
                event_id=uuid4(),
                occurred_at=now,
                actor=initiator_user_id.value,
                aggregate_type="Conversation",
                aggregate_id=conversation.id,
                payload=_message_sent_payload(conversation, first_message, recipient_user_id),
            )
        )
        await self._publisher.publish_message(
            recipient_user_id=recipient_user_id.value,
            conversation_id=conversation.id,
            message=first_message,
        )
        return conversation

    async def list_my_conversations(
        self, *, user_id: UserId, cursor: str | None, limit: int
    ) -> tuple[list[Conversation], str | None]:
        return await self._conversations.list_by_participant(
            user_id.value, cursor=cursor, limit=limit
        )

    async def get_conversation(self, conversation_id: UUID, *, user_id: UserId) -> Conversation:
        conversation = await self._require_conversation(conversation_id)
        _require_participant(conversation, user_id)
        return conversation

    async def list_messages(
        self, conversation_id: UUID, *, user_id: UserId, cursor: str | None, limit: int
    ) -> tuple[list[UUID], Conversation]:
        """Returns `(page_of_message_ids_in_order, conversation)` -- the router paginates over
        `conversation.messages` (oldest-first, per `listMessages`'s own documented ordering);
        pagination is done in-process since `Message` has no repository of its own to query
        independently (Logical Sec 18.2)."""
        conversation = await self._require_conversation(conversation_id)
        _require_participant(conversation, user_id)
        ordered_ids = [m.id for m in conversation.messages]
        if cursor is not None:
            try:
                start = ordered_ids.index(UUID(cursor)) + 1
            except ValueError:
                start = 0
        else:
            start = 0
        page_ids = ordered_ids[start : start + limit]
        return page_ids, conversation

    async def send_message(
        self, conversation_id: UUID, *, author_id: UserId, body: str, now: datetime
    ) -> Conversation:
        conversation = await self._require_conversation(conversation_id)
        _require_participant(conversation, author_id)
        recipient_id = conversation.participants.other(author_id)

        recent_count = await self._conversations.count_recent_messages_by_author(
            author_id.value, since=_rate_limit_window_start(now)
        )
        MessageRateLimitPolicy().check(recent_message_count=recent_count)

        is_sender_blocked = await self._blocks.exists(
            blocker_user_id=recipient_id.value, blocked_user_id=author_id.value
        )
        updated = conversation.send_message(
            message_id=uuid4(),
            author_id=author_id,
            body=body,
            now=now,
            is_sender_blocked=is_sender_blocked,
        )
        saved = await self._conversations.save(updated)
        new_message = saved.messages[-1]

        await self._outbox.append(
            MessageSent(
                event_id=uuid4(),
                occurred_at=now,
                actor=author_id.value,
                aggregate_type="Conversation",
                aggregate_id=saved.id,
                payload=_message_sent_payload(saved, new_message, recipient_id),
            )
        )
        await self._publisher.publish_message(
            recipient_user_id=recipient_id.value, conversation_id=saved.id, message=new_message
        )
        return saved

    async def mark_message_delivered(
        self, conversation_id: UUID, message_id: UUID, *, now: datetime
    ) -> Conversation:
        """Called only by the realtime gateway, immediately after it has actually pushed a
        message down an active WebSocket connection -- no REST operation calls this."""
        conversation = await self._require_conversation(conversation_id)
        updated = conversation.mark_message_delivered(message_id=message_id, now=now)
        return await self._conversations.save(updated)

    async def reveal_phone(
        self, conversation_id: UUID, *, requester_id: UserId, now: datetime
    ) -> str | None:
        """I-18/BRULE-13/FR-MSG-003. Returns the counterpart's phone number if their privacy
        settings permit, else `None` -- the router translates this directly into
        `PhoneRevealResponse.allowed`/`phoneNumber`, never logging the value either way (Security
        Sec 3.1 PII discipline)."""
        conversation = await self._require_conversation(conversation_id)
        _require_participant(conversation, requester_id)
        counterpart_id = conversation.participants.other(requester_id)

        phone_number = await self._contact_policy.reveal_phone(counterpart_id)
        if phone_number is not None:
            await self._outbox.append(
                PhoneRevealed(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=requester_id.value,
                    aggregate_type="Conversation",
                    aggregate_id=conversation.id,
                    payload={
                        "conversationId": str(conversation.id),
                        "revealerUserId": str(requester_id.value),
                        "revealedUserId": str(counterpart_id.value),
                    },
                )
            )
        return phone_number

    async def _require_conversation(self, conversation_id: UUID) -> Conversation:
        conversation = await self._conversations.get_by_id(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return conversation


def _require_participant(conversation: Conversation, user_id: UserId) -> None:
    if not conversation.participants.contains(user_id):
        raise NotAParticipantError(conversation.id, user_id.value)


def _rate_limit_window_start(now: datetime) -> datetime:
    return now - timedelta(seconds=MESSAGE_RATE_LIMIT_WINDOW_SECONDS)


def _chat_initiated_payload(conversation: Conversation) -> dict[str, object]:
    return {
        "conversationId": str(conversation.id),
        "listingId": str(conversation.listing.listing_id.value),
        "initiatorUserId": str(conversation.participants.initiator_user_id.value),
        "recipientUserId": str(conversation.participants.recipient_user_id.value),
    }


def _message_sent_payload(
    conversation: Conversation, message: Message, recipient_id: UserId
) -> dict[str, object]:
    return {
        "conversationId": str(conversation.id),
        "messageId": str(message.id),
        "authorUserId": str(message.author_user_id.value),
        "recipientUserId": str(recipient_id.value),
    }
