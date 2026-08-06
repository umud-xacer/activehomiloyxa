"""messaging/infrastructure -- the Redis pub/sub fan-out bus (DEC-11, SAD Sec 6: "message
fan-out via Redis pub/sub"). One channel per recipient user (`messaging:user:{userId}`), not per
conversation: a single WebSocket connection must receive every message across every conversation
its owner participates in without re-subscribing each time a new conversation starts, and no v1
document specifies a per-conversation subscription protocol. Redis is a bus, never the source of
truth -- the message is already durably persisted (`ConversationRepository.save`) before
`RedisRealtimePublisherAdapter.publish_message` is ever called; a message published while the
recipient has no active WebSocket connection is simply not delivered live (it is still fetched
on their next `listMessages` call -- NFR-REL-002's "degrade gracefully" applies here too, not
just to the whole realtime tier being down).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from redis.asyncio import Redis

from messaging.domain import Message

_CHANNEL_PREFIX = "messaging:user:"


def _channel(user_id: UUID) -> str:
    return f"{_CHANNEL_PREFIX}{user_id}"


def _message_payload(*, conversation_id: UUID, message: Message) -> str:
    return json.dumps(
        {
            "conversationId": str(conversation_id),
            "messageId": str(message.id),
            "authorUserId": str(message.author_user_id.value),
            "body": message.body,
            "sentAt": message.sent_at.isoformat(),
        }
    )


class RedisRealtimePublisherAdapter:
    """Implements `messaging.application.ports.RealtimePublisherPort`. Used by the stateless HTTP
    tier's `ConversationUseCases` -- publishing to Redis is a fire-and-forget bus write, not a
    held connection, so this does not make the HTTP tier stateful (SAD Sec 6)."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish_message(
        self, *, recipient_user_id: UUID, conversation_id: UUID, message: Message
    ) -> None:
        await self._redis.publish(
            _channel(recipient_user_id),
            _message_payload(conversation_id=conversation_id, message=message),
        )


class RedisMessageSubscriber:
    """The realtime gateway's own read side -- never used by the stateless HTTP tier. One
    subscription per authenticated WebSocket connection, opened only after the same-session
    authentication step (SAD Sec 6: "the realtime tier authenticates the same session before
    upgrading to WebSocket")."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def listen(self, user_id: UUID) -> AsyncIterator[str]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(_channel(user_id))
        try:
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                data = raw["data"]
                yield data.decode() if isinstance(data, bytes) else data
        finally:
            await pubsub.unsubscribe(_channel(user_id))
            await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis-py's PubSub stub gap
