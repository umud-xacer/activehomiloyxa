"""The catalog worker process entrypoint (Infra Sec 4's `worker` container -- deployment topology
only, no Dockerfile in this task). Was a documented, out-of-scope gap through Task P-07 (`catalog/
README.md`'s own "Known gaps" #1: `CatalogExpiryWorker`'s own docstring already referenced this
file, but it was never created); filled here, in Task P-09, because this file is now the natural
home for the SECOND independent consumer that gap's own text anticipated -- not media's outbox
(still unwired, out of this task's scope), but billing's: `provide_catalog_expiry_worker`'s own
poll loop, and `provide_catalog_entitlement_projection_dispatcher`'s `OutboxDispatcher` draining
billing's outbox into catalog's already-built `handle_entitlement_event` (ACTIVE_SUBSCRIPTION
entitlements only -- see `composition_root.py`'s own module-level note on why
EntitlementExpired/EntitlementRevoked are deliberately not routed there).

Task P-12 adds a third loop: `provide_identity_account_status_projection_dispatcher`'s
`OutboxDispatcher` draining identity's outbox into catalog's already-built `handle_identity_event`
(DB Architecture Sec 14.4's "account suspension -> listings hidden by catalog's own transition"
compensation) -- catalog is the CONSUMER of that event, so its own worker process runs the
dispatcher, the same reasoning already applied to billing's outbox above.

Run: python -m catalog_worker (from apps/backend/src, matching how `main.py`/`media_worker.py`
are invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    expiry_worker = composition_root.provide_catalog_expiry_worker()
    entitlement_dispatcher = composition_root.provide_catalog_entitlement_projection_dispatcher()
    identity_dispatcher = composition_root.provide_identity_account_status_projection_dispatcher()
    await asyncio.gather(
        expiry_worker.run_forever(),
        entitlement_dispatcher.run_forever(),
        identity_dispatcher.run_forever(),
    )


if __name__ == "__main__":
    asyncio.run(_main())
