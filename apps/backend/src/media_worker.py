"""The media intake worker process entrypoint (Task P-06; Infra Sec 4's `worker` container --
deployment topology only, no Dockerfile in this task, see `media/README.md`). Mirrors
`main.py`'s role for the `api` process: composes the real worker via the composition root and
runs it forever. No FastAPI app, no inbound network surface (Security Sec 7 "Background workers
... no inbound network surface").

Now runs a second loop alongside the intake worker: the dispatcher draining media's OWN outbox
into its two consumers (catalog's image `asset_status_snapshot` projection and profiles'
portfolio/document cleanliness projection). That table previously had no dispatcher at all, so
scan results never reached either -- see `composition_root.make_media_outbox_fanout_handler` for
why the producing module's worker owns it rather than either consumer's.

Run: python -m media_worker (from apps/backend/src, matching how `main.py` is invoked).
"""

from __future__ import annotations

import asyncio

import composition_root
from backbone.logging import configure_logging


async def _main() -> None:
    configure_logging()
    worker = composition_root.provide_media_intake_worker()
    outbox_dispatcher = composition_root.provide_media_outbox_fanout_dispatcher()
    await asyncio.gather(
        worker.run_forever(),
        outbox_dispatcher.run_forever(),
    )


if __name__ == "__main__":
    asyncio.run(_main())
