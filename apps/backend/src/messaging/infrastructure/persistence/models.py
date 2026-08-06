"""SQLAlchemy models for messaging's Postgres-backed `Conversation`/`Block` aggregates (Physical
DB Design's messaging schema, TABLES 24-26). `MessageRow` is `Conversation`'s child entity (DDD
Sec 5.7) -- no repository of its own, no `AggregateMixin` (append-only; only `delivered_at`/
`read_at` are ever mutated post-insert, matching the physical "guard trigger permits UPDATE of
delivered_at/read_at only" note) -- mirrors `catalog.infrastructure.persistence.models.
ImageAttachmentRow`'s own plain-child-row shape. `BlockRow` likewise carries no `AggregateMixin`:
`Block` has no update methods at all, only create + physical delete (Physical DB Design: "physical
DELETE on unblock permitted -- facts persist as events")."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backbone.idempotency import make_processed_event_model
from backbone.outbox import make_outbox_event_model
from backbone.persistence import AggregateMixin, uuid7
from messaging.infrastructure.persistence.base import MessagingBase

_CONVERSATION_STATUSES = "('INITIATED', 'ACTIVE', 'ARCHIVED')"


class ConversationRow(MessagingBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "conversation"

    listing_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    initiator_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    recipient_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="ACTIVE")
    last_message_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"status IN {_CONVERSATION_STATUSES}", name="ck_conversation_status"),
        CheckConstraint(
            "initiator_user_id <> recipient_user_id", name="ck_conversation_distinct_participants"
        ),
        UniqueConstraint(
            "listing_id", "initiator_user_id", name="ux_conversation_listing_initiator"
        ),
        Index("ix_conversation_initiator_last_message", "initiator_user_id", "last_message_at"),
        Index("ix_conversation_recipient_last_message", "recipient_user_id", "last_message_at"),
    )


class MessageRow(MessagingBase):  # type: ignore[misc,valid-type]
    __tablename__ = "message"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    conversation_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("messaging.conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    delivered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (Index("ix_message_conversation_sent", "conversation_id", "sent_at"),)


class BlockRow(MessagingBase):  # type: ignore[misc,valid-type]
    __tablename__ = "block"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    blocker_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    blocked_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("blocker_user_id <> blocked_user_id", name="ck_block_distinct_users"),
        UniqueConstraint("blocker_user_id", "blocked_user_id", name="ux_block_blocker_blocked"),
        Index("ix_block_blocked_user", "blocked_user_id"),
    )


class ListingOwnerProjectionRow(MessagingBase):  # type: ignore[misc,valid-type]
    """A locally projected read model of a listing's owner (`startConversation` must resolve the
    recipient from `listingId` alone -- `ConversationCreateRequest` carries no recipient field --
    but messaging may not import `catalog`). Not an aggregate -- no `AggregateMixin`, keyed by
    `listing_id` itself (the catalog-owned id, not a locally generated one), rebuilt idempotently
    from catalog's own `ListingCreated` event via `infrastructure.event_projection.
    handle_listing_created`. Mirrors `catalog.infrastructure.persistence.models.
    SubscriptionProjectionRow`'s own "cache, not an aggregate" shape exactly."""

    __tablename__ = "listing_owner_projection"

    listing_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    owner_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


OutboxEventRow = make_outbox_event_model(MessagingBase)
ProcessedEventRow = make_processed_event_model(MessagingBase)
