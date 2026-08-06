"""`SqlalchemyConversationRepository` / `SqlalchemyBlockRepository` -- implement
`application.ports`' repositories against Postgres. `Message` children are upserted via
`session.merge()` (insert-if-new, update-if-existing by PK) rather than catalog's own "replace
wholesale on every save()" strategy: unlike a listing's <=10 image attachments, a conversation's
message history only grows and is never truncated, so wholesale delete+reinsert on every
`send_message`/`mark_message_delivered` call would re-write the entire history on every single
message -- `merge()` touches only the rows that are actually new or changed.
"""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from messaging.domain import (
    Block,
    BlockPair,
    Conversation,
    ConversationStatus,
    ListingRef,
    Message,
    ParticipantPair,
)
from messaging.infrastructure.persistence.models import (
    BlockRow,
    ConversationRow,
    ListingOwnerProjectionRow,
    MessageRow,
)
from shared_kernel import ListingId, UserId


def _encode_cursor(anchor: datetime, row_id: UUID) -> str:
    raw = f"{anchor.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    anchor_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(anchor_str), UUID(row_id)


def _message_to_domain(row: MessageRow) -> Message:
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        author_user_id=UserId(value=row.author_user_id),
        body=row.body,
        sent_at=row.sent_at,
        delivered_at=row.delivered_at,
        read_at=row.read_at,
    )


def _conversation_to_domain(row: ConversationRow, message_rows: list[MessageRow]) -> Conversation:
    ordered = sorted(message_rows, key=lambda m: m.sent_at)
    return Conversation(
        id=row.id,
        listing=ListingRef(listing_id=ListingId(value=row.listing_id)),
        participants=ParticipantPair(
            initiator_user_id=UserId(value=row.initiator_user_id),
            recipient_user_id=UserId(value=row.recipient_user_id),
        ),
        status=ConversationStatus(row.status),
        messages=tuple(_message_to_domain(m) for m in ordered),
        last_message_at=row.last_message_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
    )


class SqlalchemyConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        row = await self._session.get(ConversationRow, conversation_id)
        if row is None:
            return None
        messages = (
            (
                await self._session.execute(
                    select(MessageRow).where(MessageRow.conversation_id == conversation_id)
                )
            )
            .scalars()
            .all()
        )
        return _conversation_to_domain(row, list(messages))

    async def get_by_listing_and_initiator(
        self, listing_id: UUID, initiator_user_id: UUID
    ) -> Conversation | None:
        row = (
            await self._session.execute(
                select(ConversationRow).where(
                    ConversationRow.listing_id == listing_id,
                    ConversationRow.initiator_user_id == initiator_user_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return await self.get_by_id(row.id)

    async def add(self, conversation: Conversation) -> None:
        self._session.add(
            ConversationRow(
                id=conversation.id,
                listing_id=conversation.listing.listing_id.value,
                initiator_user_id=conversation.participants.initiator_user_id.value,
                recipient_user_id=conversation.participants.recipient_user_id.value,
                status=conversation.status.value,
                last_message_at=conversation.last_message_at,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                lock_version=conversation.lock_version,
            )
        )
        for message in conversation.messages:
            self._session.add(_message_row_from_domain(message))

    async def save(self, conversation: Conversation) -> Conversation:
        row = await self._session.get(ConversationRow, conversation.id)
        if row is None:
            raise ValueError(f"conversation {conversation.id} does not exist; call add() first")
        row.status = conversation.status.value
        row.last_message_at = conversation.last_message_at
        row.updated_at = conversation.updated_at
        row.lock_version = conversation.lock_version + 1
        for message in conversation.messages:
            await self._session.merge(_message_row_from_domain(message))
        await self._session.flush()
        return await self.get_by_id(conversation.id)  # type: ignore[return-value]

    async def list_by_participant(
        self, user_id: UUID, *, cursor: str | None, limit: int
    ) -> tuple[list[Conversation], str | None]:
        stmt = select(ConversationRow).where(
            (ConversationRow.initiator_user_id == user_id)
            | (ConversationRow.recipient_user_id == user_id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()

        def _anchor(r: ConversationRow) -> datetime:
            return r.last_message_at or r.created_at

        ordered = sorted(rows, key=lambda r: (_anchor(r), r.id))
        if cursor is not None:
            anchor, row_id = _decode_cursor(cursor)
            ordered = [r for r in ordered if (_anchor(r), r.id) > (anchor, row_id)]
        page = ordered[: limit + 1]
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = _encode_cursor(_anchor(page[-1]), page[-1].id)
        conversations = [await self.get_by_id(r.id) for r in page]
        return [c for c in conversations if c is not None], next_cursor

    async def count_recent_messages_by_author(self, author_id: UUID, *, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(MessageRow)
            .where(MessageRow.author_user_id == author_id, MessageRow.sent_at >= since)
        )
        return int(result.scalar_one())


def _message_row_from_domain(message: Message) -> MessageRow:
    return MessageRow(
        id=message.id,
        conversation_id=message.conversation_id,
        author_user_id=message.author_user_id.value,
        body=message.body,
        sent_at=message.sent_at,
        delivered_at=message.delivered_at,
        read_at=message.read_at,
    )


class SqlalchemyBlockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists(self, *, blocker_user_id: UUID, blocked_user_id: UUID) -> bool:
        row = (
            await self._session.execute(
                select(BlockRow.id).where(
                    BlockRow.blocker_user_id == blocker_user_id,
                    BlockRow.blocked_user_id == blocked_user_id,
                )
            )
        ).scalar_one_or_none()
        return row is not None

    async def add(self, block: Block) -> None:
        self._session.add(
            BlockRow(
                id=block.id,
                blocker_user_id=block.pair.blocker_user_id.value,
                blocked_user_id=block.pair.blocked_user_id.value,
                created_at=block.created_at,
            )
        )

    async def delete(self, *, blocker_user_id: UUID, blocked_user_id: UUID) -> None:
        row = (
            await self._session.execute(
                select(BlockRow).where(
                    BlockRow.blocker_user_id == blocker_user_id,
                    BlockRow.blocked_user_id == blocked_user_id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)

    async def list_by_blocker(self, blocker_user_id: UUID) -> tuple[Block, ...]:
        rows = (
            (
                await self._session.execute(
                    select(BlockRow).where(BlockRow.blocker_user_id == blocker_user_id)
                )
            )
            .scalars()
            .all()
        )
        return tuple(
            Block(
                id=r.id,
                pair=BlockPair(
                    blocker_user_id=UserId(value=r.blocker_user_id),
                    blocked_user_id=UserId(value=r.blocked_user_id),
                ),
                created_at=r.created_at,
            )
            for r in rows
        )


class SqlalchemyListingOwnerProjectionReader:
    """Implements `messaging.application.ports.ListingOwnerReaderPort` against the local
    `listing_owner_projection` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owner(self, listing_id: UUID) -> UserId | None:
        row = await self._session.get(ListingOwnerProjectionRow, listing_id)
        if row is None:
            return None
        return UserId(value=row.owner_user_id)
