"""The campaign schedule sweep worker process entrypoint (Task P-14; Infra Sec 4's `worker`
container). Mirrors `billing_worker.py`'s role for the `api` process: composes the real worker
via the composition root and runs it forever. No FastAPI app, no inbound network surface.

Run: python -m ads_worker (from apps/backend/src, matching how `billing_worker.py` is invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    worker = composition_root.provide_ads_campaign_schedule_sweep_worker()
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(_main())
