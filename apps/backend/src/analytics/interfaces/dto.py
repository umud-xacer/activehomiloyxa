"""analytics -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
operations tagged to this module (contracts/openapi.yaml). Schema only: no aggregate
type is exposed here, no business behaviour, no validation beyond what Pydantic
itself does structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from active_home_shared import CamelModel


class PageInfo(CamelModel):
    """Cursor pagination metadata (OpenAPI `CursorPage.page`)."""

    limit: int
    next_cursor: str | None = None
    """Pass as `cursor` to fetch the next page; null when exhausted."""
    total: int | None = None
    """Present only where cheap to compute; may be null."""


class AuditEntry(CamelModel):
    """OpenAPI `AuditEntry`."""

    id: UUID
    actor_user_id: UUID | None = None
    action: str
    target_type: str | None = None
    target_id: UUID | None = None
    payload: dict[str, Any] | None = None
    occurred_at: datetime


class AuditEntryPage(CamelModel):
    """A cursor-paginated page of `AuditEntry` (OpenAPI `CursorPage` composed with
    `items: AuditEntry[]` via `allOf`)."""

    items: list[AuditEntry]
    page: PageInfo
