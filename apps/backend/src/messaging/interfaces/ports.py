"""messaging -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from messaging.interfaces.dto import (
    Block,
    BlockUserBody,
    Conversation,
    ConversationCreateRequest,
    ConversationPage,
    Message,
    MessageCreateRequest,
    MessagePage,
    PhoneRevealResponse,
    ReportCreateRequest,
)


class ConversationPort(Protocol):
    """Derived from OpenAPI operations: `blockUser`, `createReport`, `getConversation`, `listBlocks`, `listConversations`, `listMessages`, `revealPhone`, `sendMessage`, `startConversation`, `unblockUser`."""

    async def block_user(self, body: BlockUserBody) -> Block:
        """`POST /me/blocks` (operationId `blockUser`). Block a user"""
        ...

    async def create_report(self, body: ReportCreateRequest) -> None:
        """`POST /reports` (operationId `createReport`). Report content"""
        ...

    async def get_conversation(self, conversation_id: UUID) -> Conversation:
        """`GET /conversations/{conversationId}` (operationId `getConversation`). Get a conversation"""
        ...

    async def list_blocks(self) -> list[Block]:
        """`GET /me/blocks` (operationId `listBlocks`). List blocked users"""
        ...

    async def list_conversations(
        self, cursor: str | None = None, limit: int | None = 20
    ) -> ConversationPage:
        """`GET /conversations` (operationId `listConversations`). List my conversations"""
        ...

    async def list_messages(
        self, conversation_id: UUID, cursor: str | None = None, limit: int | None = 20
    ) -> MessagePage:
        """`GET /conversations/{conversationId}/messages` (operationId `listMessages`). List messages in a conversation"""
        ...

    async def reveal_phone(self, conversation_id: UUID) -> PhoneRevealResponse:
        """`POST /conversations/{conversationId}/phone-reveal` (operationId `revealPhone`). Reveal the counterpart's phone number"""
        ...

    async def send_message(self, conversation_id: UUID, body: MessageCreateRequest) -> Message:
        """`POST /conversations/{conversationId}/messages` (operationId `sendMessage`). Send a message"""
        ...

    async def start_conversation(self, body: ConversationCreateRequest) -> Conversation:
        """`POST /conversations` (operationId `startConversation`). Start a conversation"""
        ...

    async def unblock_user(self, user_id: UUID) -> None:
        """`DELETE /me/blocks/{userId}` (operationId `unblockUser`). Unblock a user"""
        ...
