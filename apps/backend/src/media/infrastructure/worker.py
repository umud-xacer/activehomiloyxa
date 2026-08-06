"""The media intake worker (Task P-06's "async background-worker pipeline"; Infra Sec 3's
`worker` container -- deployment topology only, no Dockerfile in this task, see
`media/README.md`). No inbound network surface (Security Sec 7 "Background workers ... no
inbound network surface") -- this is a poll loop over `MediaAssetRepository`, not an HTTP
server.

Opens one fresh `AsyncSession` per batch (`backbone.persistence.session_scope`, "one use case =
one Session = one transaction"), mirroring `backbone.outbox.dispatcher.OutboxDispatcher`'s own
`session_factory`-per-batch shape rather than holding one session open for the worker's entire
process lifetime -- the storage/scanner/processor adapters are connection-pooled and safe to
share across batches, the `AsyncSession` is not.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from backbone.outbox import OutboxWriter
from backbone.persistence import session_scope
from media.application import (
    ImageProcessingPort,
    MalwareScanPort,
    MediaProcessingUseCases,
    StoragePort,
)
from media.infrastructure.persistence import SqlalchemyMediaAssetRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class MediaIntakeWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        outbox_model: type[DeclarativeBase],
        storage: StoragePort,
        scanner: MalwareScanPort,
        processor: ImageProcessingPort,
        batch_size: int = 50,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        self._session_factory = session_factory
        self._outbox_model = outbox_model
        self._storage = storage
        self._scanner = scanner
        self._processor = processor
        self._batch_size = batch_size
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> int:
        """One scan batch, then one processing batch, in a single fresh transaction. Returns the
        total number of assets advanced (useful for tests and for deciding whether to poll
        again immediately)."""
        now = datetime.now(UTC)
        async with session_scope(self._session_factory) as session:
            use_cases = MediaProcessingUseCases(
                assets=SqlalchemyMediaAssetRepository(session),
                storage=self._storage,
                scanner=self._scanner,
                processor=self._processor,
                outbox=OutboxWriter(session, self._outbox_model),
                batch_size=self._batch_size,
            )
            scanned = await use_cases.run_scan_batch(now=now)
            processed = await use_cases.run_processing_batch(now=now)
            return scanned + processed

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                advanced = await self.run_once()
            except Exception:
                logger.exception("media intake worker batch failed")
                advanced = 0
            if advanced == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)
