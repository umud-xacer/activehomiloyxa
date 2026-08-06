"""The badge-expiry sweep worker process entrypoint (Task P-11; Infra Sec 4's `worker` container
-- deployment topology only, no Dockerfile in this task). Mirrors `billing_worker.py`'s role for
its own worker: composes the real worker via the composition root and runs it forever. No FastAPI
app, no inbound network surface (Security Sec 7 "Background workers ... no inbound network
surface"). The billing-entitlement-to-profiles projection dispatcher (X-03, I-12) is intentionally
NOT run from here -- it shares ONE dispatcher with catalog's own equivalent consumer, run from
`catalog_worker.py` (see `composition_root.make_billing_entitlement_fanout_handler`'s own
docstring for why).

Run: python -m profiles_worker (from apps/backend/src, matching how `billing_worker.py` is
invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    worker = composition_root.provide_profiles_badge_expiry_worker()
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(_main())
