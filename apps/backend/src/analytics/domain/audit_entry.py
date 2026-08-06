"""analytics/domain -- `AuditEntry` [P], the immutable administrative/moderation/configuration
fact (DDD Sec 5.13, FR-AUDIT-001, I-22). Append-only: no field is ever mutated after
construction, enforced here at the domain level (`ImmutableFactMutationError`) and again,
independently, by the database's own guard trigger (PD-07) -- see `infrastructure/persistence/
models.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from analytics.domain.exceptions import ImmutableFactMutationError
from shared_kernel import UserId


@dataclass
class AuditEntry:
    """Actor, Action, Target, Timestamp, context payload (FR-AUDIT-001). `target_type`/
    `target_id`/`actor_user_id` are bare identifiers only, never dereferenced transactionally
    (Database Architecture Sec 3.12) -- analytics stores exactly what the triggering event's own
    payload carried, it never calls back into the emitting module to enrich a fact."""

    id: UUID
    occurred_at: datetime
    action: str
    actor_user_id: UserId | None
    actor_context: str | None
    target_type: str | None
    target_id: UUID | None
    payload: dict[str, Any]
    source_event_id: UUID
    """Dedup key -- the triggering `EventEnvelope.event_id`. Persisted in
    `UNIQUE (source_event_id, occurred_at)` alongside the schema-wide `processed_event` ledger
    (Physical DB Sec 2.12)."""

    def __setattr__(self, name: str, value: object) -> None:
        raise ImmutableFactMutationError("AuditEntry")

    def __delattr__(self, name: str) -> None:
        raise ImmutableFactMutationError("AuditEntry")

    @staticmethod
    def create(
        *,
        action: str,
        actor_user_id: UserId | None,
        actor_context: str | None,
        target_type: str | None,
        target_id: UUID | None,
        payload: dict[str, Any],
        source_event_id: UUID,
        occurred_at: datetime,
        entry_id: UUID | None = None,
    ) -> AuditEntry:
        entry = AuditEntry.__new__(AuditEntry)
        object.__setattr__(entry, "id", entry_id or uuid4())
        object.__setattr__(entry, "occurred_at", occurred_at)
        object.__setattr__(entry, "action", action)
        object.__setattr__(entry, "actor_user_id", actor_user_id)
        object.__setattr__(entry, "actor_context", actor_context)
        object.__setattr__(entry, "target_type", target_type)
        object.__setattr__(entry, "target_id", target_id)
        object.__setattr__(entry, "payload", payload)
        object.__setattr__(entry, "source_event_id", source_event_id)
        return entry
