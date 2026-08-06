"""The outbox abstraction -- shared kernel (DDD Sec 5.14). Interface only: what it means to
append an event to a module's transactional outbox, in the same transaction as the aggregate
state change that caused it (DEC-09 generalised: never dual-write; Physical DB Sec 2.13
`<schema>.outbox_event`, "written in the same transaction as aggregate state"). No concrete
persistence here -- that is the owning module's `infrastructure/` adapter, built in the
persistence-backbone task.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared_kernel.events import EventEnvelope


@runtime_checkable
class OutboxPort(Protocol):
    """Implemented by each module's `infrastructure/` outbox adapter; used by `application/` use
    cases through dependency inversion (Playbook Sec 6 "use cases receive their ports, never
    construct concrete adapters"). Appending is expected to participate in the caller's current
    transaction, not open its own."""

    async def append(self, event: EventEnvelope) -> None:
        """Stage `event` for dispatch, as part of the enclosing transaction."""
        ...
