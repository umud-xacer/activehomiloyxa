"""The analytics worker process entrypoint (Task P-15; Infra Sec 4's `worker` container --
deployment topology only, no Dockerfile in this task). Mirrors `notifications_worker.py`'s role:
composes the real dispatchers/workers via the composition root and runs them forever. No FastAPI
app, no inbound network surface.

Drains CONFIGURATION's and ADS' own outbox tables -- the FIRST dispatcher either has ever had
(both previously undrained: every conforming context reads configuration synchronously via
cached snapshots, X-01, and no prior task wired anything against ads' own outbox). analytics'
OTHER five event sources (billing/catalog/identity/messaging/profiles/moderation) are folded into
those modules' own ALREADY-EXISTING combined dispatchers instead (`catalog_worker.py`/
`search_worker.py`/`moderation_worker.py`/`notifications_worker.py`) -- only one dispatcher may
safely drain a given outbox table, so analytics' own consumer joins whichever dispatcher already
owns that table rather than racing it (see `composition_root.py`'s own per-handler docstrings for
exactly which worker process now also carries an analytics route). Also runs the
partition-precreate scheduled job (Physical DB Sec 2/Sec 16).

Run: python -m analytics_worker (from apps/backend/src, matching how `main.py`/`ads_worker.py`
are invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    configuration_dispatcher = (
        composition_root.provide_analytics_configuration_projection_dispatcher()
    )
    ads_dispatcher = composition_root.provide_analytics_ads_projection_dispatcher()
    partition_worker = composition_root.provide_analytics_partition_precreate_worker()
    await asyncio.gather(
        configuration_dispatcher.run_forever(),
        ads_dispatcher.run_forever(),
        partition_worker.run_forever(),
    )


if __name__ == "__main__":
    asyncio.run(_main())
