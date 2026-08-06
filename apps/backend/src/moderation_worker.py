"""The moderation worker process entrypoint (Task P-12; Infra Sec 4's `worker` container --
deployment topology only, no Dockerfile in this task). Mirrors `media_worker.py`'s role for the
media intake worker: composes the real dispatcher via the composition root and runs it forever.
No FastAPI app, no inbound network surface (Security Sec 7 "Background workers ... no inbound
network surface"). Drains MESSAGING's own outbox (`ContentReported` -> `handle_content_reported`,
FR-MOD-001/FR-MSG-005) -- moderation's other real event source, catalog's `ListingFlagged`, is
folded into catalog's own combined outbox dispatcher instead (`composition_root.
make_catalog_outbox_fanout_handler`'s own docstring explains why: only one dispatcher may safely
drain a given outbox table, and catalog's already has one, run by `search_worker.py`).

Run: python -m moderation_worker (from apps/backend/src, matching how `main.py`/`media_worker.py`
are invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    dispatcher = composition_root.provide_moderation_report_projection_dispatcher()
    await dispatcher.run_forever()


if __name__ == "__main__":
    asyncio.run(_main())
