"""Eventual-consistency proof for "catalog listing events -> search index projection": a real
`Listing` aggregate, published, with its own real outbox event, drained through search's REAL
`make_search_event_handler` (the SAME closure `composition_root.make_catalog_outbox_fanout_
handler` attaches in production) -> indexed into a real OpenSearch document, searchable by title.

This is the end-to-end proof for the P-20 fix to search/README.md's own "CONFIRMED payload gap
blocking real content indexing" (catalog's `_listing_payload()` used to omit every field
`handle_listing_published` needs) -- not just that the payload SHAPE is now correct, but that a
real produced event actually converges into a real, queryable OpenSearch document.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import uuid4

import pytest
import pytest_asyncio
from opensearchpy import OpenSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from catalog.application import ListingUseCases
from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ListingType
from catalog.infrastructure.persistence.base import CatalogBase
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.infrastructure.persistence.repository import (
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from contracts.events.catalog import ListingPublished
from search.domain import SearchQuery, SortOption
from search.infrastructure.event_projection import make_search_event_handler
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from shared_kernel import EventEnvelope, ListingId, UserId
from tests.integration.conftest import ensure_clean_schema, poll_until

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OPENSEARCH_AVAILABLE = bool(os.environ.get("OPENSEARCH_HOST"))
_INDEX_NAME = "listing_search_content_test"


@pytest.fixture(autouse=True)
def _skip_without_opensearch() -> None:
    if not OPENSEARCH_AVAILABLE:
        pytest.skip("OPENSEARCH_HOST not set -- no real OpenSearch cluster to test against")


@pytest_asyncio.fixture(autouse=True)
async def _catalog_schema(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "catalog", CatalogBase)


@pytest_asyncio.fixture
async def opensearch_index() -> AsyncIterator[OpenSearchIndexAdapter]:
    client = OpenSearch(
        hosts=[
            {
                "host": os.environ["OPENSEARCH_HOST"],
                "port": int(os.environ.get("OPENSEARCH_PORT", "9200")),
            }
        ]
    )
    adapter = OpenSearchIndexAdapter(client, index_name=_INDEX_NAME)
    await adapter.delete_index()
    await adapter.ensure_index()
    yield adapter
    await adapter.delete_index()


class _UnusedCategoryFormPort:
    async def get_category(self, category_id: object) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def get_current_form_binding(self, category_id: object) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedPlatformSettingsReaderPort:
    async def get_catalog_settings(self) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedMediaAssetReaderPort:
    async def get_media_asset(self, media_asset_id: object) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedCreditBalancePort:
    async def consume_one_listing_credit(self, *, owner_profile_id: object) -> NoReturn:
        raise AssertionError("not exercised by this test")


async def test_a_real_listing_published_event_is_indexed_and_becomes_searchable(
    session_factory: async_sessionmaker[AsyncSession],
    opensearch_index: OpenSearchIndexAdapter,
) -> None:
    owner_id = UserId(value=uuid4())
    listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=owner_id,
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/real-estate/apartments",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="Cozy studio near metro",
        description="Fully furnished studio, 5 minutes from the metro station",
        attributes={"rooms": "1"},
        price=None,
        location=None,
        slug="cozy-studio-near-metro",
        now=NOW,
    ).publish(
        record_id=uuid4(),
        actor_user_id=owner_id.value,
        expires_at=NOW + timedelta(days=30),
        now=NOW,
    )

    async with session_factory() as session:
        listings_repo = SqlalchemyListingRepository(session)
        await listings_repo.add(listing)
        outbox = OutboxWriter(session, CatalogOutboxEventRow)
        # Reuses catalog's own real `_listing_payload()` (the P-20-widened one) via a throwaway
        # `ListingUseCases` instance so the payload shape can never drift from what production
        # actually sends -- this test seeds the aggregate directly rather than going through the
        # full create-draft-then-publish flow, mirroring `test_moderation_listing_compensation.
        # py`'s own established pattern.
        use_cases = ListingUseCases(
            listings=listings_repo,
            categories=_UnusedCategoryFormPort(),
            settings=_UnusedPlatformSettingsReaderPort(),
            media=_UnusedMediaAssetReaderPort(),
            outbox=outbox,
            quota=QuotaEnforcementService(
                subscriptions=SqlalchemySubscriptionSnapshotRepository(session)
            ),
            duplicates=DuplicateDetectionService(listings=listings_repo),
            credit_balance=_UnusedCreditBalancePort(),
        )
        await outbox.append(
            ListingPublished(
                event_id=uuid4(),
                occurred_at=NOW,
                actor=owner_id.value,
                aggregate_type="Listing",
                aggregate_id=listing.id.value,
                payload=await use_cases._listing_payload(listing),
            )
        )
        await session.commit()

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(CatalogOutboxEventRow).where(
                        CatalogOutboxEventRow.event_type == "ListingPublished"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )

    search_handler = make_search_event_handler(
        session_factory=session_factory, index=opensearch_index
    )
    await search_handler(envelope)

    async def _indexed() -> bool:
        return await opensearch_index.get_document(listing.id.value) is not None

    await poll_until(_indexed, timeout_seconds=5.0)
    document = await opensearch_index.get_document(listing.id.value)
    assert document is not None
    assert document.title == "Cozy studio near metro"
    assert document.slug == "cozy-studio-near-metro"

    await asyncio.to_thread(
        opensearch_index._client.indices.refresh,
        index=opensearch_index._index_name,
    )
    page = await opensearch_index.search(
        SearchQuery(
            q="studio",
            category_id=None,
            owner_profile_id=None,
            listing_type=None,
            filters={},
            price_min=None,
            price_max=None,
            verified_only=False,
            geo=None,
            sort=SortOption.RELEVANCE,
            cursor=None,
            limit=20,
        ),
        facet_specs=(),
    )
    assert listing.id.value in {hit.document.listing_id for hit in page.hits}
