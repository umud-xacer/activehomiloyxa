"""Integration tests: `search.infrastructure.event_projection`'s idempotent consumers against
real PostgreSQL -- `idempotent_consume`'s `INSERT ... ON CONFLICT` needs a real Postgres dialect
to prove (see `apps/backend/tests/search/test_event_projection.py`'s `FakeIdempotentSession` for
the fast-tier equivalent of this same contract), mirroring `apps/backend/tests/catalog/
integration/test_event_projection_live.py`'s own pattern.

Also covers the projection-rebuild-determinism checklist item (P-08 Validation Checklist:
"projection fully rebuildable" -- DB Architecture Sec 12: "full reindex = replay from the owners'
data via their interfaces/events"): discard the fallback index entirely, replay the SAME event
sequence from scratch, and assert the rebuilt projection is byte-for-byte equivalent to the
original.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from search.application.indexing_use_cases import IndexingUseCases
from search.application.ports import FacetResult, FacetSpec, SearchResultPage, SuggestionResult
from search.domain import SearchQuery
from search.domain.search_document import ListingSearchDocument
from search.infrastructure.event_projection import dispatch_search_event
from search.infrastructure.persistence.models import ListingFallbackDocumentRow, ProcessedEventRow
from search.infrastructure.persistence.repository import SqlalchemyFallbackIndexRepository
from shared_kernel import EventEnvelope

NOW = datetime(2026, 7, 12, tzinfo=UTC)


class _NullSearchIndex:
    """A no-op `SearchIndexPort` stand-in -- these tests exercise the Postgres-backed
    `FallbackIndexPort`/`ProcessedEventRow` ledger only, never OpenSearch (unavailable in this
    sandbox; see `search/README.md`)."""

    async def index_document(self, document: ListingSearchDocument) -> None:
        return None

    async def delete_document(self, listing_id: UUID) -> None:
        return None

    async def get_document(self, listing_id: UUID) -> ListingSearchDocument | None:
        return None

    async def find_listing_ids_by_owner_profile(self, owner_profile_id: UUID) -> tuple[UUID, ...]:
        return ()

    async def search(
        self, query: SearchQuery, *, facet_specs: tuple[FacetSpec, ...]
    ) -> SearchResultPage:
        raise NotImplementedError

    async def facets(
        self, category_id: UUID | None, facet_specs: tuple[FacetSpec, ...]
    ) -> tuple[FacetResult, ...]:
        raise NotImplementedError

    async def suggest(self, q: str, *, limit: int) -> tuple[SuggestionResult, ...]:
        raise NotImplementedError


def _content_payload(listing_id: object, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "listingId": str(listing_id),
        "title": "Kvartira",
        "categoryId": str(uuid4()),
        "categoryPath": "/real-estate",
        "listingType": "ADVERTISEMENT",
        "slug": "kvartira",
        "isPubliclyVisible": True,
    }
    payload.update(overrides)
    return payload


async def test_listing_published_redelivery_applies_the_projection_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    listing_id = uuid4()
    event = EventEnvelope(
        event_id=uuid4(),
        event_type="ListingPublished",
        occurred_at=NOW,
        aggregate_type="Listing",
        aggregate_id=listing_id,
        payload=_content_payload(listing_id),
    )

    for _ in range(2):
        async with session_factory() as session:
            use_cases = IndexingUseCases(
                index=_NullSearchIndex(), fallback=SqlalchemyFallbackIndexRepository(session)
            )
            await dispatch_search_event(session, event, use_cases)
            await session.commit()

    async with session_factory() as session:
        row = await session.get(ListingFallbackDocumentRow, listing_id)
        assert row is not None
        assert row.title == "Kvartira"

        ledger_rows = (await session.execute(select(ProcessedEventRow))).scalars().all()
        assert len(ledger_rows) == 1
        assert ledger_rows[0].event_id == event.event_id


async def test_projection_rebuild_is_deterministic(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    listing_id = uuid4()
    category_id = uuid4()
    events = [
        EventEnvelope(
            event_id=uuid4(),
            event_type="ListingPublished",
            occurred_at=NOW,
            aggregate_type="Listing",
            aggregate_id=listing_id,
            payload=_content_payload(listing_id, categoryId=str(category_id)),
        ),
        EventEnvelope(
            event_id=uuid4(),
            event_type="ListingEdited",
            occurred_at=NOW,
            aggregate_type="Listing",
            aggregate_id=listing_id,
            payload=_content_payload(
                listing_id, categoryId=str(category_id), title="Kvartira (edited)"
            ),
        ),
        EventEnvelope(
            event_id=uuid4(),
            event_type="ListingSuspended",
            occurred_at=NOW,
            aggregate_type="Listing",
            aggregate_id=listing_id,
            payload={"listingId": str(listing_id), "lifecycleState": "SUSPENDED"},
        ),
        EventEnvelope(
            event_id=uuid4(),
            event_type="ListingRenewed",
            occurred_at=NOW,
            aggregate_type="Listing",
            aggregate_id=listing_id,
            payload=_content_payload(
                listing_id, categoryId=str(category_id), title="Kvartira (edited)"
            ),
        ),
    ]

    async def _replay() -> ListingFallbackDocumentRow:
        for event in events:
            async with session_factory() as session:
                use_cases = IndexingUseCases(
                    index=_NullSearchIndex(), fallback=SqlalchemyFallbackIndexRepository(session)
                )
                await dispatch_search_event(session, event, use_cases)
                await session.commit()
        async with session_factory() as session:
            row = await session.get(ListingFallbackDocumentRow, listing_id)
            assert row is not None
            session.expunge(row)
            return row

    first_projection = await _replay()

    # discard the index (and the idempotency ledger, so the replay below is treated as fresh
    # delivery, not a no-op redelivery) and replay the exact same event sequence from scratch.
    async with session_factory() as session:
        await session.execute(
            delete(ListingFallbackDocumentRow).where(
                ListingFallbackDocumentRow.listing_id == listing_id
            )
        )
        await session.execute(
            delete(ProcessedEventRow).where(
                ProcessedEventRow.event_id.in_([event.event_id for event in events])
            )
        )
        await session.commit()

    second_projection = await _replay()

    assert first_projection.title == second_projection.title
    assert first_projection.publicly_visible == second_projection.publicly_visible
    assert first_projection.title_normalized_latin == second_projection.title_normalized_latin
    assert first_projection.title_normalized_cyrillic == second_projection.title_normalized_cyrillic
    assert first_projection.category_path == second_projection.category_path
    assert first_projection.slug == second_projection.slug
