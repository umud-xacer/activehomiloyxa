"""analytics/application -- `AuditUseCases` (FR-AUDIT-001/002, I-22). Recording is called from
inside an idempotent event consumer (`infrastructure/event_projection.py`); querying backs
`GET /admin/audit-log` (operationId `queryAuditLog`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from analytics.application.ports import AuditEntryRepository
from analytics.domain import AuditEntry
from shared_kernel import UserId


class AuditUseCases:
    def __init__(self, *, entries: AuditEntryRepository) -> None:
        self._entries = entries

    async def record_audit_fact(
        self,
        *,
        action: str,
        actor_user_id: UserId | None,
        actor_context: str | None,
        target_type: str | None,
        target_id: UUID | None,
        payload: dict[str, Any],
        source_event_id: UUID,
        occurred_at: datetime,
    ) -> AuditEntry:
        """# enforces I-22: "every administrative, moderation, and configuration action yields an
        immutable AuditEntry." Called once per triggering event, from inside the caller's own
        `idempotent_consume` block -- redelivery of the same `source_event_id` never reaches here
        twice (see `infrastructure/event_projection.py`)."""
        entry = AuditEntry.create(
            action=action,
            actor_user_id=actor_user_id,
            actor_context=actor_context,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            source_event_id=source_event_id,
            occurred_at=occurred_at,
        )
        await self._entries.add(entry)
        return entry

    async def query_audit_log(
        self,
        *,
        actor_user_id: UUID | None = None,
        target_type: str | None = None,
        action: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[AuditEntry], str | None]:
        """FR-AUDIT-002: "the system SHALL allow authorised administrators to view audit logs...
        logs are viewable and filterable." Read-only -- no mutation path exists anywhere on this
        use-case class."""
        return await self._entries.query(
            actor_user_id=actor_user_id,
            target_type=target_type,
            action=action,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            cursor=cursor,
            limit=limit,
        )
