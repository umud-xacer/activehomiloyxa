"""messaging/infrastructure -- projects catalog's own `ListingCreated` event into messaging's
local `listing_owner_projection` (I-01: `owner_user_id` is fixed for life, so a single
observation of `ListingCreated` is sufficient -- no later listing event ever needs to be
consumed to keep this projection correct). Catalog never imports messaging and vice versa
(AIR-10) -- this is the async, outbox-driven, one-way read side of that boundary, mirroring
`catalog.infrastructure.event_projection.handle_entitlement_event`'s own precedent exactly.

CRITICAL WIRING NOTE (see `messaging/README.md` "Known gaps" for the full write-up): catalog's
own `outbox_event` table already has exactly one consumer wired at the composition root
(`search.infrastructure.worker.SearchIndexingWorker`'s own `catalog_outbox_model` dispatcher,
Task P-08) -- `backbone.outbox.dispatcher.OutboxDispatcher` claims rows by mutating a SHARED
`dispatch_status` column, so a second, independent `OutboxDispatcher` instance draining the SAME
table would race with search's for every row (including `ListingCreated`, which search's own
handler ignores but still marks `DISPATCHED` when it wins the race) -- catalog's own README
`Known gaps` #1 already anticipated exactly this: "a future task adding a second independent
consumer ... would need a different mechanism". `composition_root.py`'s
`make_catalog_outbox_fanout_handler` is that mechanism: ONE dispatcher on catalog's outbox, whose
handler calls BOTH search's own routing AND `handle_listing_created` below -- neither `search/`
nor `catalog/` is modified, only composition-root wiring."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backbone.idempotency import idempotent_consume
from messaging.infrastructure.persistence.models import ListingOwnerProjectionRow, ProcessedEventRow
from shared_kernel import EventEnvelope

_LISTING_OWNER_HANDLER = "messaging.listing_owner_projection"


async def handle_listing_created(session: AsyncSession, envelope: EventEnvelope) -> None:
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_LISTING_OWNER_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        listing_id_raw = envelope.payload.get("listingId")
        owner_user_id_raw = envelope.payload.get("ownerUserId")
        if listing_id_raw is None or owner_user_id_raw is None:
            return
        row = await session.get(ListingOwnerProjectionRow, UUID(str(listing_id_raw)))
        if row is None:
            session.add(
                ListingOwnerProjectionRow(
                    listing_id=UUID(str(listing_id_raw)),
                    owner_user_id=UUID(str(owner_user_id_raw)),
                )
            )
