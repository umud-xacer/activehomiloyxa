"""Integration tests: `OpenSearchIndexAdapter` against a real OpenSearch cluster (`deployment/
compose/docker-compose.yml`'s `opensearch` service). Skips gracefully when `OPENSEARCH_HOST` isn't
set -- unlike `POSTGRES_HOST`, this repo's CI workflow (`.github/workflows/ci.yml`, QG-03) does not
currently spin up an OpenSearch service container, so this file only ever runs against a local
`scripts/dev-up.sh` environment; the fast, no-cluster-needed equivalent of everything here
(`_document_to_source`/`_source_to_document`/`_build_query_body`) lives in
`apps/backend/tests/search/test_opensearch_index.py` and DOES run in CI.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from opensearchpy import OpenSearch

from search.domain import ListingType, PromotionKind, PromotionMarker, SearchQuery, SortOption
from search.domain.search_document import ListingSearchDocument
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from shared_kernel import GeoLocation, Money

pytestmark = pytest.mark.integration

OPENSEARCH_AVAILABLE = bool(os.environ.get("OPENSEARCH_HOST"))
_INDEX_NAME = "listing_search_test"
_NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _skip_without_opensearch() -> None:
    if not OPENSEARCH_AVAILABLE:
        pytest.skip("OPENSEARCH_HOST not set -- no real OpenSearch cluster to test against")


@pytest_asyncio.fixture
async def adapter() -> AsyncIterator[OpenSearchIndexAdapter]:
    client = OpenSearch(
        hosts=[
            {
                "host": os.environ["OPENSEARCH_HOST"],
                "port": int(os.environ.get("OPENSEARCH_PORT", "9200")),
            }
        ]
    )
    instance = OpenSearchIndexAdapter(client, index_name=_INDEX_NAME)
    await instance.delete_index()
    await instance.ensure_index()
    yield instance
    await instance.delete_index()


def _document(**overrides: object) -> ListingSearchDocument:
    kwargs: dict[str, object] = {
        "listing_id": uuid4(),
        "owner_profile_id": uuid4(),
        "title": "Kvartira sotiladi",
        "description": "3-xonali kvartira",
        "category_id": uuid4(),
        "category_path": "/real-estate/apartments",
        "listing_type": ListingType.ADVERTISEMENT,
        "attributes": {"rooms": "3"},
        "price": Money(amount=Decimal("50000.00"), currency="USD"),
        "location": GeoLocation(latitude=41.2995, longitude=69.2401),
        "verified_badge": False,
        "publicly_visible": True,
        "slug": "kvartira-sotiladi",
        "published_at": _NOW,
        "updated_at": _NOW,
    }
    kwargs.update(overrides)
    return ListingSearchDocument.project(**kwargs)  # type: ignore[arg-type]


def _query(**overrides: object) -> SearchQuery:
    kwargs: dict[str, object] = {
        "q": None,
        "category_id": None,
        "owner_profile_id": None,
        "listing_type": None,
        "filters": {},
        "price_min": None,
        "price_max": None,
        "verified_only": False,
        "geo": None,
        "sort": SortOption.RELEVANCE,
        "cursor": None,
        "limit": 20,
    }
    kwargs.update(overrides)
    return SearchQuery(**kwargs)  # type: ignore[arg-type]


async def test_index_then_get_document_round_trips(adapter: OpenSearchIndexAdapter) -> None:
    document = _document()
    await adapter.index_document(document)
    fetched = await adapter.get_document(document.listing_id)
    assert fetched == document


async def test_get_document_returns_none_for_an_unindexed_listing(
    adapter: OpenSearchIndexAdapter,
) -> None:
    assert await adapter.get_document(uuid4()) is None


async def test_delete_document_removes_it(adapter: OpenSearchIndexAdapter) -> None:
    document = _document()
    await adapter.index_document(document)
    await adapter.delete_document(document.listing_id)
    assert await adapter.get_document(document.listing_id) is None


async def test_cross_script_search_matches_a_cyrillic_query_against_latin_content(
    adapter: OpenSearchIndexAdapter,
) -> None:
    document = _document(title="Kvartira")
    await adapter.index_document(document)
    await asyncio.to_thread(adapter._client.indices.refresh, index=adapter._index_name)

    page = await adapter.search(_query(q="квартира"), facet_specs=())
    assert document.listing_id in {hit.document.listing_id for hit in page.hits}


async def test_geo_radius_search_finds_a_nearby_listing(adapter: OpenSearchIndexAdapter) -> None:
    from search.domain import GeoFilter

    tashkent = GeoLocation(latitude=41.2995, longitude=69.2401)
    document = _document(location=tashkent)
    await adapter.index_document(document)
    await asyncio.to_thread(adapter._client.indices.refresh, index=adapter._index_name)

    page = await adapter.search(
        _query(geo=GeoFilter(center=tashkent, radius_km=5.0)), facet_specs=()
    )
    assert document.listing_id in {hit.document.listing_id for hit in page.hits}


async def test_promoted_documents_survive_the_full_index_search_round_trip(
    adapter: OpenSearchIndexAdapter,
) -> None:
    entitlement_id = uuid4()
    document = _document(title="Featured listing").with_promotion(
        promotion=PromotionMarker(
            kind=PromotionKind.FEATURED, valid_until=None, entitlement_id=entitlement_id
        ),
        updated_at=_NOW,
    )
    await adapter.index_document(document)
    fetched = await adapter.get_document(document.listing_id)
    assert fetched is not None
    assert fetched.promotion is not None
    assert fetched.promotion.entitlement_id == entitlement_id


async def test_find_listing_ids_by_owner_profile_fans_out_correctly(
    adapter: OpenSearchIndexAdapter,
) -> None:
    owner_profile_id = uuid4()
    first = _document(owner_profile_id=owner_profile_id)
    second = _document(owner_profile_id=owner_profile_id)
    unrelated = _document(owner_profile_id=uuid4())
    for document in (first, second, unrelated):
        await adapter.index_document(document)
    await asyncio.to_thread(adapter._client.indices.refresh, index=adapter._index_name)

    listing_ids = await adapter.find_listing_ids_by_owner_profile(owner_profile_id)
    assert set(listing_ids) == {first.listing_id, second.listing_id}
