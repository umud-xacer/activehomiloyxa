"""The idempotent-consumer helper (Logical Sec 18 "Idempotency is data. Every consumer keys on
event identity via its ProcessedEvent ledger before acting"; Physical DB Sec 13: "consumers open
a transaction of processed_event insert + local effect + own outbox rows -- the ledger conflict
(PK violation) is the idempotency signal, treated as SKIPPED, never an error").

The check-and-record is one atomic `INSERT ... ON CONFLICT DO NOTHING` on the composite primary
key `(event_id, handler)` -- not a separate SELECT-then-INSERT, which would race under
concurrent redelivery.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import DeclarativeBase


@asynccontextmanager
async def idempotent_consume(
    session: AsyncSession,
    model: type[DeclarativeBase],
    *,
    event_id: UUID,
    handler: str,
) -> AsyncIterator[bool]:
    """Yields `True` on a fresh delivery -- the caller proceeds with its handler logic and its
    own outbox writes on this same `session`, all committed together with the ledger row by the
    caller's own transaction boundary. Yields `False` when `(event_id, handler)` was already
    recorded: redelivery is a no-op, and the caller must not repeat side effects.

    Does not commit and does not catch the caller's exceptions -- if the wrapped logic raises,
    the whole transaction (ledger row included) rolls back, so the next delivery attempt sees a
    fresh, unrecorded event again (retryable, per SAD Sec 11), not a permanently "used up" id.
    """
    stmt = (
        pg_insert(model)
        .values(event_id=event_id, handler=handler, result="APPLIED")
        .on_conflict_do_nothing(index_elements=["event_id", "handler"])
    )
    result = await session.execute(stmt)
    # `AsyncSession.execute()` is typed to return the generic `CursorResult`'s parent
    # `Result[Any]`, which doesn't statically expose `.rowcount` even though the concrete object
    # returned for an INSERT always is a `CursorResult` at runtime.
    is_fresh_delivery = result.rowcount > 0  # type: ignore[attr-defined]
    yield is_fresh_delivery
