"""The outbox dispatcher (SAD Sec 11 "Background Processing": "a dispatcher drains it and
routes to idempotent workers ... Workers are idempotent and retryable; an event may be
delivered more than once, so consumers key on event identity."). Background process only -- no
inbound API surface; instantiate and run it from a worker entrypoint script, never from a
FastAPI router.

Redelivery safety is the *consumer's* job (`backbone.idempotency`), not the dispatcher's: this
class's contract is at-least-once delivery to `handler`, matching SAD Sec 11 literally. A
handler that is not itself idempotent is a defect in the handler, not here.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from shared_kernel import EventEnvelope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


def _row_to_envelope(row: object) -> EventEnvelope:
    return EventEnvelope(
        event_id=row.id,  # type: ignore[attr-defined]
        event_type=row.event_type,  # type: ignore[attr-defined]
        occurred_at=row.occurred_at,  # type: ignore[attr-defined]
        actor=row.actor,  # type: ignore[attr-defined]
        aggregate_type=row.aggregate_type,  # type: ignore[attr-defined]
        aggregate_id=row.aggregate_id,  # type: ignore[attr-defined]
        aggregate_version=row.aggregate_version,  # type: ignore[attr-defined]
        payload=row.payload,  # type: ignore[attr-defined]
    )


class OutboxDispatcher:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        model: type[DeclarativeBase],
        handler: EventHandler,
        *,
        batch_size: int = 50,
        max_attempts: int = 5,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._session_factory = session_factory
        self._model = model
        self._handler = handler
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._poll_interval_seconds = poll_interval_seconds

    async def drain_once(self) -> int:
        """Claims and processes one batch of PENDING rows. `FOR UPDATE SKIP LOCKED` lets
        multiple dispatcher instances run concurrently without double-claiming the same row
        (Physical DB Sec 13's contention pattern, applied here to outbox draining)."""
        async with self._session_factory() as session, session.begin():
            stmt = (
                select(self._model)
                .where(self._model.dispatch_status == "PENDING")  # type: ignore[attr-defined]
                .order_by(self._model.created_at)  # type: ignore[attr-defined]
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            rows = (await session.execute(stmt)).scalars().all()

            for row in rows:
                envelope = _row_to_envelope(row)
                try:
                    await self._handler(envelope)
                except Exception:
                    row.attempts += 1  # type: ignore[attr-defined]
                    if row.attempts >= self._max_attempts:  # type: ignore[attr-defined]
                        row.dispatch_status = "DEAD"  # type: ignore[attr-defined]
                    logger.exception(
                        "outbox event dispatch failed",
                        extra={
                            "event_id": str(envelope.event_id),
                            "event_type": envelope.event_type,
                        },
                    )
                else:
                    row.dispatch_status = "DISPATCHED"  # type: ignore[attr-defined]
                    row.dispatched_at = datetime.now(UTC)  # type: ignore[attr-defined]

            return len(rows)

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Polls until `stop_event` is set (tests set it after N iterations; a real worker
        entrypoint runs this unbounded)."""
        while stop_event is None or not stop_event.is_set():
            processed = await self.drain_once()
            if processed == 0:
                await asyncio.sleep(self._poll_interval_seconds)
