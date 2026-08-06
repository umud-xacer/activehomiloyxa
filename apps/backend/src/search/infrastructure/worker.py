"""The search indexing worker (SAD Sec 3/9: "the read path never blocks on another context";
Deliverables: "indexing runs in a background worker, the write path never writes to OpenSearch
directly"). No inbound network surface -- like `catalog.infrastructure.worker.CatalogExpiryWorker`
and `media.infrastructure.worker.MediaIntakeWorker`, this is a poll loop, not an HTTP server.

Unlike those two precedents, this worker's job is not to sweep search's OWN repository for
locally-pending work -- it is to DRAIN other modules' `outbox_event` tables (catalog's today;
billing's/profiles' once P-09/P-11 exist), via one `backbone.outbox.dispatcher.OutboxDispatcher`
per producing module, all sharing the single routing handler `search.infrastructure.
event_projection.make_search_event_handler` builds. `SearchIndexingWorker` never imports
`catalog`/`billing`/`profiles` itself (the CRITICAL BOUNDARY RULE applies to this file exactly as
to every other file in `search/`) -- each producing module's own outbox ORM class is supplied by
the composition root (the one place allowed to see every module's internals) as a constructor
argument, typed only as `type[DeclarativeBase]`, the same mechanism `CatalogExpiryWorker`/
`MediaIntakeWorker` already use for their own `outbox_model` parameter (there, to WRITE; here, to
READ -- the type itself carries no direction).

`billing_outbox_model`/`profiles_outbox_model` default to `None`: BC-08/BC-02 do not exist yet, so
there is no outbox table to drain for them. `SearchIndexingWorker` runs correctly with only
`catalog_outbox_model` supplied -- the entitlement/badge handlers remain fully implemented and
unit-tested against synthetic envelopes (see `search/README.md` "Known gaps"), simply with no
dispatcher wired to invoke them in production until those modules ship."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from backbone.outbox import OutboxDispatcher
from search.infrastructure.event_projection import make_search_event_handler

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase

    from search.application.ports import SearchIndexPort

logger = logging.getLogger(__name__)


class SearchIndexingWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        index: SearchIndexPort,
        catalog_outbox_model: type[DeclarativeBase],
        billing_outbox_model: type[DeclarativeBase] | None = None,
        profiles_outbox_model: type[DeclarativeBase] | None = None,
        batch_size: int = 50,
        max_attempts: int = 5,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        handler = make_search_event_handler(session_factory=session_factory, index=index)
        outbox_models = [catalog_outbox_model, billing_outbox_model, profiles_outbox_model]
        self._dispatchers = [
            OutboxDispatcher(
                session_factory,
                model,
                handler,
                batch_size=batch_size,
                max_attempts=max_attempts,
            )
            for model in outbox_models
            if model is not None
        ]
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> int:
        """Drains one batch from every configured producing module's outbox in turn. Returns the
        total number of rows claimed (across all dispatchers) -- used by tests and to decide
        whether to poll again immediately rather than sleeping."""
        total = 0
        for dispatcher in self._dispatchers:
            total += await dispatcher.drain_once()
        return total

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                processed = await self.run_once()
            except Exception:
                logger.exception("search indexing worker batch failed")
                processed = 0
            if processed == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)
