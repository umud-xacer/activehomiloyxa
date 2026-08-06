"""The entitlement expiry sweep worker (FR-SUBS-004/I-15; "using the P-03 worker framework" --
the poll-loop shape `catalog.infrastructure.worker.CatalogExpiryWorker`/`media.infrastructure.
worker.MediaIntakeWorker` already established: `run_once()`/`run_forever(stop_event)`, a fresh
`AsyncSession` per batch via `backbone.persistence.session_scope`). No inbound network surface --
a poll loop over `EntitlementRepository.list_expiring_active`, not an HTTP server.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from backbone.outbox import OutboxWriter
from backbone.persistence import session_scope
from billing.application import EntitlementUseCases
from billing.infrastructure.persistence.repository import (
    SqlalchemyEntitlementRepository,
    SqlalchemyOrderRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class EntitlementExpiryWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        outbox_model: type[DeclarativeBase],
        batch_size: int = 50,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self._session_factory = session_factory
        self._outbox_model = outbox_model
        self._batch_size = batch_size
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> int:
        """One expiry sweep batch in a single fresh transaction. Returns the number of
        entitlements swept (state-transition + outbox event append committed together per
        entitlement, DEC-09) -- NOT the sanctioned three-aggregate synchronous exception (that is
        `PaymentUseCases.confirm_payment`'s own, scoped there only)."""
        now = datetime.now(UTC)
        async with session_scope(self._session_factory) as session:
            use_cases = EntitlementUseCases(
                entitlements=SqlalchemyEntitlementRepository(session),
                orders=SqlalchemyOrderRepository(session),
                outbox=OutboxWriter(session, self._outbox_model),
            )
            return await use_cases.sweep_expired(now=now, batch_size=self._batch_size)

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                swept = await self.run_once()
            except Exception:
                logger.exception("entitlement expiry sweep batch failed")
                swept = 0
            if swept == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)
