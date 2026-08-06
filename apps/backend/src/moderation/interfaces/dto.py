"""moderation -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
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


class ModerationActionRequest(CamelModel):
    """OpenAPI `ModerationActionRequest`."""

    action: Literal[
        "HIDE",
        "REJECT",
        "SUSPEND",
        "REQUEST_CORRECTION",
        "REMOVE",
        "SUSPEND_ACCOUNT",
        "DISMISS",
        "REVOKE_BADGE",
        "ARCHIVE_PROFILE",
    ]
    """Closed verb set (BR-MOD-02, extended by ADR-0003 with `REVOKE_BADGE`/`ARCHIVE_PROFILE`)."""
    note: str | None = None


class ModerationCase(CamelModel):
    """OpenAPI `ModerationCase`."""

    id: UUID
    subject_type: Literal["LISTING", "CONVERSATION", "USER", "PROFILE"]
    subject_id: UUID
    origin_type: Literal["USER_REPORT", "AUTOMATED_FLAG"]
    report_reason: str | None = None
    rule_key: str | None = None
    status: Literal["OPEN", "IN_REVIEW", "RESOLVED"]
    resolution_action: (
        Literal[
            "HIDE",
            "REJECT",
            "SUSPEND",
            "REQUEST_CORRECTION",
            "REMOVE",
            "SUSPEND_ACCOUNT",
            "DISMISS",
            "REVOKE_BADGE",
            "ARCHIVE_PROFILE",
        ]
        | None
    ) = None
    created_at: datetime


class ModerationCasePage(CamelModel):
    """A cursor-paginated page of `ModerationCase` (OpenAPI `CursorPage` composed with
    `items: ModerationCase[]` via `allOf`)."""

    items: list[ModerationCase]
    page: PageInfo
