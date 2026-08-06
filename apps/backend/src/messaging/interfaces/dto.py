"""messaging -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
operations tagged to this module (contracts/openapi.yaml). Schema only: no aggregate
type is exposed here, no business behaviour, no validation beyond what Pydantic
itself does structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from active_home_shared import CamelModel


class PageInfo(CamelModel):
    """Cursor pagination metadata (OpenAPI `CursorPage.page`)."""

    limit: int
    next_cursor: str | None = None
    """Pass as `cursor` to fetch the next page; null when exhausted."""
    total: int | None = None
    """Present only where cheap to compute; may be null."""


class BlockUserBody(CamelModel):
    """OpenAPI `BlockUserBody`."""

    blocked_user_id: UUID


class Block(CamelModel):
    """OpenAPI `Block`."""

    blocked_user_id: UUID
    created_at: datetime | None = None


class ReportCreateRequest(CamelModel):
    """OpenAPI `ReportCreateRequest`."""

    subject_type: Literal["LISTING", "CONVERSATION", "USER"]
    subject_id: UUID
    reason: str


class Conversation(CamelModel):
    """OpenAPI `Conversation`."""

    id: UUID
    listing_id: UUID
    initiator_user_id: UUID
    recipient_user_id: UUID
    status: Literal["INITIATED", "ACTIVE", "ARCHIVED"]
    last_message_at: datetime | None = None
    created_at: datetime


class ConversationPage(CamelModel):
    """A cursor-paginated page of `Conversation` (OpenAPI `CursorPage` composed with
    `items: Conversation[]` via `allOf`)."""

    items: list[Conversation]
    page: PageInfo


class Message(CamelModel):
    """OpenAPI `Message`."""

    id: UUID
    conversation_id: UUID
    author_user_id: UUID
    body: str
    sent_at: datetime
    delivered_at: datetime | None = None
    read_at: datetime | None = None


class MessagePage(CamelModel):
    """A cursor-paginated page of `Message` (OpenAPI `CursorPage` composed with
    `items: Message[]` via `allOf`)."""

    items: list[Message]
    page: PageInfo


class PhoneRevealResponse(CamelModel):
    """OpenAPI `PhoneRevealResponse`."""

    allowed: bool
    """False when the owner's privacy settings block reveal (BRULE-13)."""
    phone_number: str | None = None
    """Present only when allowed."""


class MessageCreateRequest(CamelModel):
    """OpenAPI `MessageCreateRequest`."""

    body: str


class ConversationCreateRequest(CamelModel):
    """OpenAPI `ConversationCreateRequest`."""

    listing_id: UUID
    message: str
