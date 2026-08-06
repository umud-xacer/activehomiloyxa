"""The entitlement expiry sweep worker process entrypoint (Task P-09; Infra Sec 4's `worker`
container -- deployment topology only, no Dockerfile in this task). Mirrors `main.py`'s role for
the `api` process, and `media_worker.py`'s/`search_worker.py`'s role for their own workers:
composes the real worker via the composition root and runs it forever. No FastAPI app, no
inbound network surface (Security Sec 7 "Background workers ... no inbound network surface").

Run: python -m billing_worker (from apps/backend/src, matching how `main.py`/`media_worker.py`
are invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    worker = composition_root.provide_billing_entitlement_expiry_worker()
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(_main())
