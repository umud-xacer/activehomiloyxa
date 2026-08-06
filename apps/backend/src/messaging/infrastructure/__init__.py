"""messaging/infrastructure -- SQLAlchemy repositories and the Redis pub/sub fan-out adapters
(Task P-10). Never imported by `messaging.interfaces`/`application`/`domain` -- only the
composition root (outside every module's package tree) wires these concrete classes behind the
ports `application/` declares."""

from __future__ import annotations

from messaging.infrastructure.event_projection import handle_listing_created
from messaging.infrastructure.persistence import (
    BlockRow,
    ConversationRow,
    ListingOwnerProjectionRow,
    MessageRow,
    MessagingBase,
    OutboxEventRow,
    ProcessedEventRow,
    SqlalchemyBlockRepository,
    SqlalchemyConversationRepository,
    SqlalchemyListingOwnerProjectionReader,
)
from messaging.infrastructure.realtime import RedisMessageSubscriber, RedisRealtimePublisherAdapter

__all__ = [
    "BlockRow",
    "ConversationRow",
    "ListingOwnerProjectionRow",
    "MessageRow",
    "MessagingBase",
    "OutboxEventRow",
    "ProcessedEventRow",
    "RedisMessageSubscriber",
    "RedisRealtimePublisherAdapter",
    "SqlalchemyBlockRepository",
    "SqlalchemyConversationRepository",
    "SqlalchemyListingOwnerProjectionReader",
    "handle_listing_created",
]
