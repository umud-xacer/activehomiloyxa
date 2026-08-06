"""The notifications worker process entrypoint (Task P-13; Infra Sec 4's `worker` container --
deployment topology only, no Dockerfile in this task). Mirrors `moderation_worker.py`'s role:
composes the real dispatchers via the composition root and runs them forever. No FastAPI app, no
inbound network surface (Security Sec 7 "Background workers ... no inbound network surface").

Drains PROFILES' and MODERATION's own outbox tables -- the FIRST dispatcher either has ever had
(both were previously undrained, documented gaps in their own READMEs). notifications' OTHER
five event sources (identity/catalog/billing/messaging, plus ads' still-unwired stub) are folded
into those modules' own ALREADY-EXISTING combined dispatchers instead (`catalog_worker.py`/
`search_worker.py`/`moderation_worker.py`) -- only one dispatcher may safely drain a given outbox
table, so notifications' own consumer joins whichever dispatcher already owns that table rather
than racing it (see `composition_root.py`'s own per-handler docstrings for exactly which worker
process now also carries a notifications route).

Run: python -m notifications_worker (from apps/backend/src, matching how `main.py`/
`media_worker.py` are invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    profiles_dispatcher = composition_root.provide_profiles_notification_projection_dispatcher()
    moderation_dispatcher = composition_root.provide_moderation_notification_projection_dispatcher()
    await asyncio.gather(
        profiles_dispatcher.run_forever(),
        moderation_dispatcher.run_forever(),
    )


if __name__ == "__main__":
    asyncio.run(_main())
