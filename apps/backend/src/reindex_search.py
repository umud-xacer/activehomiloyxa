"""One-off / re-runnable backfill: replays every currently publicly-visible `catalog.listing` row
straight into the search projection (OpenSearch + its Postgres fallback table), bypassing the
catalog outbox entirely.

Why this exists: the outbox-driven path (`search_worker.py` draining `ListingPublished`/
`ListingEdited` events) is the steady-state mechanism, but it only sees listings published/edited
*while the worker is running*. Any listing that became PUBLISHED/EDITED before the worker was ever
started (or while it was down) has no outstanding outbox row to replay -- its event was already
marked DISPATCHED (if a worker existed before) or its outbox row predates this environment's
history entirely. `search/README.md`'s own "full reindex = replay from the owners' data via their
interfaces/events" (DB Architecture Sec 12) licenses exactly this: catalog's OWN current data is
just as valid a replay source as its historical events, since the search index is a pure,
disposable projection of catalog.

Also fixes a real mapping bug: `OpenSearchIndexAdapter.index_document` does a bare `client.index()`
call, which lets OpenSearch auto-create the index with inferred (wrong) field types if `ensure_index`
was never called first -- notably `location` as a plain `{lat, lon}` object instead of `geo_point`,
which breaks geo-distance queries/sorting. This script deletes and recreates the index against the
real `INDEX_MAPPING` before repopulating it, so a stale auto-inferred mapping never lingers.

Run (from apps/backend/src, matching search_worker.py/main.py's own invocation convention):
    python -m reindex_search
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import composition_root
from backbone.logging import configure_logging
from search.application.indexing_use_cases import IndexingUseCases
from search.domain import ListingType
from search.infrastructure.persistence.repository import SqlalchemyFallbackIndexRepository


async def _main() -> None:
    configure_logging()
    now = datetime.now(UTC)

    index_adapter = composition_root._search_index_adapter()
    print("Deleting existing (possibly mismapped) index...")
    await index_adapter.delete_index()
    print(
        "Recreating index with the real mapping (geo_point, facet keyword templates, ru analyzer)..."
    )
    await index_adapter.ensure_index()

    total = 0
    async for catalog_session in composition_root._catalog_session():
        listing_use_cases = composition_root._build_listing_use_cases(catalog_session)
        listings_repo = listing_use_cases._listings

        cursor: str | None = None
        while True:
            page, cursor = await listings_repo.list_public(
                category_id=None, listing_type=None, cursor=cursor, limit=100, now=now
            )
            if not page:
                break

            async for search_session in composition_root._search_session():
                indexing = IndexingUseCases(
                    index=index_adapter,
                    fallback=SqlalchemyFallbackIndexRepository(search_session),
                )
                for listing in page:
                    thumbnail_url = await listing_use_cases._primary_image_thumbnail_url(listing)
                    await indexing.upsert_listing_content(
                        listing_id=listing.id.value,
                        owner_profile_id=(
                            listing.owner_profile_id.value if listing.owner_profile_id else None
                        ),
                        title=listing.title,
                        description=listing.description,
                        category_id=listing.category_id,
                        category_path=listing.category_path,
                        listing_type=ListingType(listing.listing_type.value),
                        attributes=listing.attributes,
                        price=listing.price,
                        location=listing.location,
                        slug=listing.slug,
                        published_at=listing.published_at,
                        publicly_visible=listing.is_publicly_visible(now=now),
                        primary_image_thumbnail_url=thumbnail_url,
                        now=now,
                    )
                    total += 1
                    print(f"  indexed {listing.id.value} -- {listing.title!r}")
                break  # one search session per page is enough; closing the loop commits it

            if cursor is None:
                break
        break  # one catalog session for the whole run is enough

    print(f"Done. Reindexed {total} publicly-visible listings.")


if __name__ == "__main__":
    asyncio.run(_main())
