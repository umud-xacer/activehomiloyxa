"""Degradation proof (NFR-REL-002, `DegradationPolicy [P]`): when OpenSearch is unreachable,
`SearchUseCases.search` never raises -- it degrades to the REAL PostgreSQL trigram/geo fallback
(`search.listing_fallback_document`, `SqlalchemyFallbackIndexRepository`) and returns
`degraded=True`. Uses a REAL `opensearchpy.OpenSearch` client pointed at a closed local port
(connection refused immediately, no artificial mock) so `OpenSearchIndexAdapter`'s own real
`except TransportError: raise SearchIndexUnavailableError()` translation
(`search/infrastructure/opensearch_index.py`) is genuinely exercised -- not a stubbed-out
`SearchIndexPort` that skips straight to raising the application-level exception.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest_asyncio
from opensearchpy import OpenSearch
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from search.application.ports import SearchConfigurationSnapshot
from search.application.search_use_cases import SearchUseCases
from search.domain import ListingType, SearchQuery, SortOption
from search.domain.search_document import ListingSearchDocument
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from search.infrastructure.persistence.base import SearchBase
from search.infrastructure.persistence.repository import (
    SqlalchemyFallbackIndexRepository,
)
from tests.integration.conftest import ensure_clean_schema

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _search_schema(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "search", SearchBase)


@pytest_asyncio.fixture
async def unreachable_opensearch_index() -> AsyncIterator[OpenSearchIndexAdapter]:
    """A real client pointed at a port nothing listens on -- `max_retries=0`/short `timeout` so
    connection refusal surfaces immediately as `TransportError` rather than hanging or retrying."""
    client = OpenSearch(
        hosts=[{"host": "127.0.0.1", "port": 1}],
        timeout=1,
        max_retries=0,
        retry_on_timeout=False,
    )
    yield OpenSearchIndexAdapter(client, index_name="unreachable-index")


class _FixedSearchConfigurationSnapshot:
    async def get_search_configuration(
        self, category_id: object | None
    ) -> SearchConfigurationSnapshot:
        return SearchConfigurationSnapshot(
            facet_field_codes=("rooms",),
            sort_options=(SortOption.RELEVANCE, SortOption.RECENCY),
            default_sort=SortOption.RELEVANCE,
            promotion_page_cap=3,
        )


async def test_search_degrades_to_the_postgres_fallback_when_opensearch_is_unreachable(
    session_factory: async_sessionmaker[AsyncSession],
    unreachable_opensearch_index: OpenSearchIndexAdapter,
) -> None:
    listing_id = uuid4()
    document = ListingSearchDocument.project(
        listing_id=listing_id,
        owner_profile_id=None,
        title="Fallback-findable studio",
        description=None,
        category_id=uuid4(),
        category_path="/real-estate/apartments",
        listing_type=ListingType.ADVERTISEMENT,
        attributes={},
        price=None,
        location=None,
        verified_badge=False,
        publicly_visible=True,
        slug="fallback-findable-studio",
        published_at=NOW,
        updated_at=NOW,
    )

    async with session_factory() as session:
        await SqlalchemyFallbackIndexRepository(session).upsert_document(document)
        await session.commit()

    async with session_factory() as session:
        use_cases = SearchUseCases(
            index=unreachable_opensearch_index,
            fallback=SqlalchemyFallbackIndexRepository(session),
            configuration=_FixedSearchConfigurationSnapshot(),
        )
        outcome = await use_cases.search(
            SearchQuery(
                q="studio",
                category_id=None,
                listing_type=None,
                filters={},
                price_min=None,
                price_max=None,
                verified_only=False,
                geo=None,
                sort=SortOption.RELEVANCE,
                cursor=None,
                limit=20,
            )
        )

    assert outcome.degraded is True
    assert listing_id in {hit.document.listing_id for hit in outcome.hits}
    # DB Architecture Sec 12: facet DIMENSIONS survive degradation (from configuration), bucket
    # COUNTS never do (the fallback path has no aggregation query).
    assert [facet.field_code for facet in outcome.facets] == ["rooms"]
    assert all(facet.buckets == () for facet in outcome.facets)
