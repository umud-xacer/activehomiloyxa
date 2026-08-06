"""Integration test: a message published via `RedisRealtimePublisherAdapter` (the HTTP tier's own
`send_message`/`start_conversation` side effect) is delivered to `RedisMessageSubscriber.listen`
(the realtime gateway's own read side) over REAL Redis pub/sub, AND is separately persisted to
REAL PostgreSQL via `SqlalchemyConversationRepository` -- both assertions are required (DEC-11/
Validation Checklist: "Messages are persisted to PostgreSQL AND fanned out via Redis pub/sub;
Redis is a bus, never the source of truth"). Mirrors `apps/backend/tests/identity/integration/
test_session_store_live.py`'s pattern of exercising the real Redis-backed adapter directly,
without needing a running FastAPI/WebSocket server.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from messaging.domain import Conversation, ListingRef, ParticipantPair
from messaging.infrastructure.persistence.repository import SqlalchemyConversationRepository
from messaging.infrastructure.realtime import RedisMessageSubscriber, RedisRealtimePublisherAdapter
from shared_kernel import ListingId, UserId

NOW = datetime(2026, 7, 12, tzinfo=UTC)


async def test_a_published_message_is_delivered_over_redis_and_persisted_to_postgres(
    db_session: AsyncSession, redis_client: Redis
) -> None:
    initiator = UserId(value=uuid4())
    recipient = UserId(value=uuid4())
    conversation = Conversation.start(
        conversation_id=uuid4(),
        message_id=uuid4(),
        listing=ListingRef(listing_id=ListingId(value=uuid4())),
        participants=ParticipantPair(initiator_user_id=initiator, recipient_user_id=recipient),
        initial_body="hello there",
        now=NOW,
        is_blocked=False,
    )

    # persistence (PostgreSQL is the source of truth) -----------------------------------------
    repo = SqlalchemyConversationRepository(db_session)
    await repo.add(conversation)
    await db_session.commit()

    # delivery (Redis is a bus) -----------------------------------------------------------------
    subscriber = RedisMessageSubscriber(redis_client)
    received: list[str] = []

    async def _subscribe_and_collect_one() -> None:
        async for raw in subscriber.listen(recipient.value):
            received.append(raw)
            return

    subscribe_task = asyncio.ensure_future(_subscribe_and_collect_one())
    await asyncio.sleep(0.2)  # let the SUBSCRIBE actually register before publishing

    publisher = RedisRealtimePublisherAdapter(redis_client)
    await publisher.publish_message(
        recipient_user_id=recipient.value,
        conversation_id=conversation.id,
        message=conversation.messages[0],
    )

    await asyncio.wait_for(subscribe_task, timeout=5.0)

    assert len(received) == 1
    payload = json.loads(received[0])
    assert payload["conversationId"] == str(conversation.id)
    assert payload["messageId"] == str(conversation.messages[0].id)
    assert payload["body"] == "hello there"

    reloaded = await repo.get_by_id(conversation.id)
    assert reloaded is not None
    assert reloaded.messages[0].body == "hello there"
