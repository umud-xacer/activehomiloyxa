"""FastAPI routers implementing exactly the ten messaging-tagged OpenAPI operations
(`contracts/openapi.yaml`): `listConversations`, `startConversation`, `getConversation`,
`listMessages`, `sendMessage`, `revealPhone`, `listBlocks`, `blockUser`, `unblockUser`,
`createReport`. Part of the STATELESS HTTP tier only (DEC-11) -- the realtime gateway
(`apps/backend/src/realtime_main.py`) is a separate FastAPI app mounting `interfaces/ws.py`
instead, sharing these same `application/` use cases, never this router module. Thin translation
only: path/body -> use case call -> domain object -> already-frozen `interfaces/dto.py` DTO. All
business logic lives in `application`/`domain`; this module owns none.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from messaging.application import BlockUseCases, ConversationUseCases, ReportUseCases
from messaging.domain import Block, Conversation, Message
from messaging.interfaces.auth import ActingUser
from messaging.interfaces.di import (
    get_acting_user,
    get_block_use_cases,
    get_conversation_use_cases,
    get_report_use_cases,
)
from messaging.interfaces.dto import (
    Block as BlockDto,
)
from messaging.interfaces.dto import (
    BlockUserBody,
    ConversationCreateRequest,
    ConversationPage,
    MessageCreateRequest,
    MessagePage,
    PageInfo,
    PhoneRevealResponse,
    ReportCreateRequest,
)
from messaging.interfaces.dto import (
    Conversation as ConversationDto,
)
from messaging.interfaces.dto import (
    Message as MessageDto,
)
from shared_kernel import UserId

messaging_router = APIRouter(tags=["Messaging"])


def _clamp_limit(limit: int | None) -> int:
    return min(max(limit or 20, 1), 100)


def _to_conversation_dto(conversation: Conversation) -> ConversationDto:
    return ConversationDto(
        id=conversation.id,
        listing_id=conversation.listing.listing_id.value,
        initiator_user_id=conversation.participants.initiator_user_id.value,
        recipient_user_id=conversation.participants.recipient_user_id.value,
        status=conversation.status.value,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
    )


def _to_message_dto(message: Message) -> MessageDto:
    return MessageDto(
        id=message.id,
        conversation_id=message.conversation_id,
        author_user_id=message.author_user_id.value,
        body=message.body,
        sent_at=message.sent_at,
        delivered_at=message.delivered_at,
        read_at=message.read_at,
    )


def _to_block_dto(block: Block) -> BlockDto:
    return BlockDto(blocked_user_id=block.pair.blocked_user_id.value, created_at=block.created_at)


@messaging_router.get("/conversations", operation_id="listConversations")
async def list_conversations(
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    user: ActingUser = Depends(get_acting_user),
    use_cases: ConversationUseCases = Depends(get_conversation_use_cases),
) -> ConversationPage:
    page_limit = _clamp_limit(limit)
    conversations, next_cursor = await use_cases.list_my_conversations(
        user_id=user.account_id, cursor=cursor, limit=page_limit
    )
    return ConversationPage(
        items=[_to_conversation_dto(c) for c in conversations],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


@messaging_router.post("/conversations", operation_id="startConversation", status_code=201)
async def start_conversation(
    body: ConversationCreateRequest,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ConversationUseCases = Depends(get_conversation_use_cases),
) -> ConversationDto:
    conversation = await use_cases.start_conversation(
        initiator_user_id=user.account_id,
        listing_id=body.listing_id,
        message_body=body.message,
        now=datetime.now(UTC),
    )
    return _to_conversation_dto(conversation)


@messaging_router.get("/conversations/{conversationId}", operation_id="getConversation")
async def get_conversation(
    conversationId: UUID,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ConversationUseCases = Depends(get_conversation_use_cases),
) -> ConversationDto:
    conversation = await use_cases.get_conversation(conversationId, user_id=user.account_id)
    return _to_conversation_dto(conversation)


@messaging_router.get("/conversations/{conversationId}/messages", operation_id="listMessages")
async def list_messages(
    conversationId: UUID,
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    user: ActingUser = Depends(get_acting_user),
    use_cases: ConversationUseCases = Depends(get_conversation_use_cases),
) -> MessagePage:
    page_limit = _clamp_limit(limit)
    page_ids, conversation = await use_cases.list_messages(
        conversationId, user_id=user.account_id, cursor=cursor, limit=page_limit
    )
    by_id = {m.id: m for m in conversation.messages}
    items = [_to_message_dto(by_id[mid]) for mid in page_ids]
    next_cursor = str(page_ids[-1]) if len(page_ids) == page_limit else None
    return MessagePage(items=items, page=PageInfo(limit=page_limit, next_cursor=next_cursor))


@messaging_router.post(
    "/conversations/{conversationId}/messages", operation_id="sendMessage", status_code=201
)
async def send_message(
    conversationId: UUID,
    body: MessageCreateRequest,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ConversationUseCases = Depends(get_conversation_use_cases),
) -> MessageDto:
    conversation = await use_cases.send_message(
        conversationId, author_id=user.account_id, body=body.body, now=datetime.now(UTC)
    )
    return _to_message_dto(conversation.messages[-1])


@messaging_router.post("/conversations/{conversationId}/phone-reveal", operation_id="revealPhone")
async def reveal_phone(
    conversationId: UUID,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ConversationUseCases = Depends(get_conversation_use_cases),
) -> PhoneRevealResponse:
    phone_number = await use_cases.reveal_phone(
        conversationId, requester_id=user.account_id, now=datetime.now(UTC)
    )
    return PhoneRevealResponse(allowed=phone_number is not None, phone_number=phone_number)


@messaging_router.get("/me/blocks", operation_id="listBlocks")
async def list_blocks(
    user: ActingUser = Depends(get_acting_user),
    use_cases: BlockUseCases = Depends(get_block_use_cases),
) -> list[BlockDto]:
    blocks = await use_cases.list_my_blocks(blocker_user_id=user.account_id)
    return [_to_block_dto(b) for b in blocks]


@messaging_router.post("/me/blocks", operation_id="blockUser", status_code=201)
async def block_user(
    body: BlockUserBody,
    user: ActingUser = Depends(get_acting_user),
    use_cases: BlockUseCases = Depends(get_block_use_cases),
) -> BlockDto:
    block = await use_cases.block_user(
        blocker_user_id=user.account_id,
        blocked_user_id=UserId(value=body.blocked_user_id),
        now=datetime.now(UTC),
    )
    return _to_block_dto(block)


@messaging_router.delete("/me/blocks/{userId}", operation_id="unblockUser", status_code=204)
async def unblock_user(
    userId: UUID,
    user: ActingUser = Depends(get_acting_user),
    use_cases: BlockUseCases = Depends(get_block_use_cases),
) -> None:
    await use_cases.unblock_user(
        blocker_user_id=user.account_id, blocked_user_id=UserId(value=userId)
    )


@messaging_router.post("/reports", operation_id="createReport", status_code=202)
async def create_report(
    body: ReportCreateRequest,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ReportUseCases = Depends(get_report_use_cases),
) -> None:
    await use_cases.create_report(
        reporter_id=user.account_id,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        reason=body.reason,
        now=datetime.now(UTC),
    )
