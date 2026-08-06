"""The transactional outbox writer (DEC-09: never dual-write). Structurally satisfies
`shared_kernel.OutboxPort` -- `async def append(self, event: EventEnvelope) -> None` -- so a
module's `infrastructure/` layer can type its dependency as the port and receive this at the
composition root (Playbook Sec 6 "use cases receive their ports, never construct concrete
adapters").

Deliberately does not commit: `append()` only stages the row on the session already open for
the current unit of work (Physical DB Sec 13 "one use case = one Session = one transaction =
one aggregate + its outbox rows"). The aggregate's own state changes and this row therefore
commit or roll back together by construction -- there is no separate commit call to forget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from shared_kernel import EventEnvelope

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase


class OutboxWriter:
    def __init__(self, session: AsyncSession, model: type[DeclarativeBase]) -> None:
        self._session = session
        self._model = model

    async def append(self, event: EventEnvelope) -> None:
        row = self._model(
            id=event.event_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            actor=event.actor,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            aggregate_version=event.aggregate_version,
            payload=event.payload,
        )
        self._session.add(row)
