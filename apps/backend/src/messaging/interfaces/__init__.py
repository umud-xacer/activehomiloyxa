"""messaging.interfaces -- the module's only importable public surface (AIR-02)."""

from __future__ import annotations

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
from messaging.interfaces.errors import register_messaging_exception_mappings
from messaging.interfaces.ports import (
    ConversationPort,
)
from messaging.interfaces.routers import messaging_router
from messaging.interfaces.ws import realtime_router

__all__ = [
    "Block",
    "BlockUserBody",
    "Conversation",
    "ConversationCreateRequest",
    "ConversationPage",
    "ConversationPort",
    "Message",
    "MessageCreateRequest",
    "MessagePage",
    "PhoneRevealResponse",
    "ReportCreateRequest",
    "messaging_router",
    "realtime_router",
    "register_messaging_exception_mappings",
]
