"""The domain-event envelope -- shared kernel (DDD Sec 5.14, Sec 6; Physical DB Sec 2.13
`<schema>.outbox_event`). Every event in `contracts/events/` carries exactly these fields; field
names and nullability match the `outbox_event` table's envelope columns 1:1 so the future
outbox-writer adapter is a direct mapping, not a translation.

Events are named in past tense and published through the emitting context's transactional
outbox (DEC-09 generalised: never dual-write) -- this module defines the envelope shape only,
not the publishing mechanism (that is outbox/adapter work, out of scope here).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventEnvelope(BaseModel):
    """event id, type, occurred-at, actor, aggregate ref, version (DDD Sec 5.14)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    event_type: str
    occurred_at: datetime
    actor: UUID | None = None
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int | None = None
    payload: dict[str, Any]
    """Identifier-carrying fact payload -- never object graphs (Physical DB Sec 2.13)."""
