"""The search indexing worker process entrypoint (Task P-08; Infra Sec 4's `worker` container --
deployment topology only, no Dockerfile in this task). Mirrors `main.py`'s role for the `api`
process, and `media_worker.py`'s role for the media intake worker: composes the real worker via
the composition root and runs it forever. No FastAPI app, no inbound network surface (Security
Sec 7 "Background workers ... no inbound network surface").

Task P-10 update: runs `provide_catalog_outbox_fanout_dispatcher()` instead of a directly
constructed `SearchIndexingWorker` -- see that function's own docstring (`composition_root.py`)
for why catalog's outbox now has exactly one combined dispatcher (search's own event routing
plus messaging's listing-owner projection) rather than `SearchIndexingWorker`'s own internal one.

Run: python -m search_worker (from apps/backend/src, matching how `main.py`/`media_worker.py` are
invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    dispatcher = composition_root.provide_catalog_outbox_fanout_dispatcher()
    await dispatcher.run_forever()


if __name__ == "__main__":
    asyncio.run(_main())
