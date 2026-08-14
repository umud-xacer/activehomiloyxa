"""The badge-expiry and trial-expiry sweep worker process entrypoint (Task P-11 / ADR-0010;
Infra Sec 4's `worker` container -- deployment topology only, no Dockerfile in this task). Mirrors
`billing_worker.py`'s role for its own worker: composes the real workers via the composition root
and runs both forever as independent tasks. No FastAPI app, no inbound network surface (Security
Sec 7 "Background workers ... no inbound network surface"). The billing-entitlement-to-profiles
projection dispatcher (X-03, I-12) is intentionally NOT run from here -- it shares ONE dispatcher
with catalog's own equivalent consumer, run from `catalog_worker.py` (see
`composition_root.make_billing_entitlement_fanout_handler`'s own docstring for why).

Run: python -m profiles_worker (from apps/backend/src, matching how `billing_worker.py` is
invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    badge_worker = composition_root.provide_profiles_badge_expiry_worker()
    trial_worker = composition_root.provide_profiles_trial_expiry_worker()
    await asyncio.gather(badge_worker.run_forever(), trial_worker.run_forever())


if __name__ == "__main__":
    asyncio.run(_main())
