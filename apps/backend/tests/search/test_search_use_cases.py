"""`search.application.search_use_cases.SearchUseCases` -- `DegradationPolicy [P]` (NFR-REL-002)
and `PromotionCapAndLabelPolicy [P]` (I-17) both run here, uniformly, regardless of which port
ultimately served the request; facet/sort behaviour is entirely driven by the
`SearchConfigurationSnapshot` the fixture supplies, never hardcoded."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from search.application.ports import FacetBucketResult, FacetResult, SuggestionResult
from search.application.search_use_cases import SearchUseCases
from search.domain import ListingType, PromotionKind, PromotionMarker, SearchQuery, SortOption
from search.domain.search_document import ListingSearchDocument

from .conftest import FakeConfigurationSnapshotPort, FakeFallbackIndex, FakeSearchIndex

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _document(
    *, promoted: bool = False, visible: bool = True, **overrides: object
) -> ListingSearchDocument:
    kwargs: dict[str, object] = {
        "listing_id": uuid4(),
        "owner_profile_id": None,
        "title": "Kvartira",
        "description": None,
        "category_id": uuid4(),
        "category_path": "/real-estate",
        "listing_type": ListingType.ADVERTISEMENT,
        "attributes": {},
        "price": None,
        "location": None,
        "verified_badge": False,
        "publicly_visible": visible,
        "slug": "kvartira",
        "published_at": _NOW,
        "updated_at": _NOW,
    }
    kwargs.update(overrides)
    document = ListingSearchDocument.project(**kwargs)  # type: ignore[arg-type]
    if promoted:
        document = document.with_promotion(
            promotion=PromotionMarker(
                kind=PromotionKind.PREMIUM, valid_until=None, entitlement_id=uuid4()
            ),
            updated_at=_NOW,
        )
    return document


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


@pytest.fixture
def use_cases(
    fake_index: FakeSearchIndex,
    fake_fallback: FakeFallbackIndex,
    fake_configuration: FakeConfigurationSnapshotPort,
) -> SearchUseCases:
    return SearchUseCases(
        index=fake_index, fallback=fake_fallback, configuration=fake_configuration
    )


class TestSearchHappyPath:
    @pytest.mark.asyncio
    async def test_I01_returns_hits_from_the_primary_index_when_available(
        self, use_cases: SearchUseCases, fake_index: FakeSearchIndex
    ) -> None:
        document = _document()
        fake_index.documents[document.listing_id] = document
        outcome = await use_cases.search(_query())
        assert [hit.document.listing_id for hit in outcome.hits] == [document.listing_id]
        assert outcome.degraded is False

    @pytest.mark.asyncio
    async def test_I02_never_returns_a_non_publicly_visible_document(
        self, use_cases: SearchUseCases, fake_index: FakeSearchIndex
    ) -> None:
        hidden = _document(visible=False)
        fake_index.documents[hidden.listing_id] = hidden
        outcome = await use_cases.search(_query())
        assert outcome.hits == []


class TestDegradationPolicy:
    """NFR-REL-002: "if search is unavailable it SHALL fall back to a basic query" -- no error,
    `degraded=True` on the response instead."""

    @pytest.mark.asyncio
    async def test_I03_falls_back_to_postgres_when_the_index_is_unavailable(
        self,
        use_cases: SearchUseCases,
        fake_index: FakeSearchIndex,
        fake_fallback: FakeFallbackIndex,
    ) -> None:
        fake_index.unavailable = True
        document = _document()
        fake_fallback.documents[document.listing_id] = document
        outcome = await use_cases.search(_query())
        assert outcome.degraded is True
        assert [hit.document.listing_id for hit in outcome.hits] == [document.listing_id]

    @pytest.mark.asyncio
    async def test_I04_never_raises_when_the_index_is_unavailable(
        self, use_cases: SearchUseCases, fake_index: FakeSearchIndex
    ) -> None:
        fake_index.unavailable = True
        outcome = await use_cases.search(_query())
        assert outcome.hits == []
        assert outcome.degraded is True

    @pytest.mark.asyncio
    async def test_I05_facets_degrade_to_configured_dimensions_with_empty_buckets(
        self, use_cases: SearchUseCases, fake_index: FakeSearchIndex
    ) -> None:
        fake_index.unavailable = True
        facets = await use_cases.facets(None)
        assert [f.field_code for f in facets] == ["condition", "rooms"]
        assert all(f.buckets == () for f in facets)

    @pytest.mark.asyncio
    async def test_I06_suggest_degrades_to_an_empty_tuple(
        self, use_cases: SearchUseCases, fake_index: FakeSearchIndex
    ) -> None:
        fake_index.unavailable = True
        suggestions = await use_cases.suggest("kvar", limit=5)
        assert suggestions == ()


class TestPromotionCap:
    """I-17, applied uniformly by `SearchUseCases`, regardless of which port served the request."""

    @pytest.mark.asyncio
    async def test_I07_caps_promoted_hits_at_the_configured_page_cap(
        self,
        use_cases: SearchUseCases,
        fake_index: FakeSearchIndex,
        fake_configuration: FakeConfigurationSnapshotPort,
    ) -> None:
        fake_configuration.snapshot = FakeConfigurationSnapshotPort().snapshot.__class__(
            facet_field_codes=(),
            sort_options=(SortOption.RELEVANCE,),
            default_sort=SortOption.RELEVANCE,
            promotion_page_cap=1,
        )
        promoted_docs = [_document(promoted=True) for _ in range(3)]
        for document in promoted_docs:
            fake_index.documents[document.listing_id] = document
        outcome = await use_cases.search(_query())
        promoted_hits = [hit for hit in outcome.hits if hit.is_promoted]
        assert len(promoted_hits) == 1

    @pytest.mark.asyncio
    async def test_I08_the_cap_also_applies_on_the_fallback_path(
        self,
        use_cases: SearchUseCases,
        fake_index: FakeSearchIndex,
        fake_fallback: FakeFallbackIndex,
        fake_configuration: FakeConfigurationSnapshotPort,
    ) -> None:
        fake_index.unavailable = True
        fake_configuration.snapshot = FakeConfigurationSnapshotPort().snapshot.__class__(
            facet_field_codes=(),
            sort_options=(SortOption.RELEVANCE,),
            default_sort=SortOption.RELEVANCE,
            promotion_page_cap=0,
        )
        promoted_docs = [_document(promoted=True) for _ in range(2)]
        for document in promoted_docs:
            fake_fallback.documents[document.listing_id] = document
        outcome = await use_cases.search(_query())
        assert all(not hit.is_promoted for hit in outcome.hits)


class TestFacetConfigDriven:
    @pytest.mark.asyncio
    async def test_I09_search_requests_facets_for_exactly_the_configured_field_codes(
        self, use_cases: SearchUseCases, fake_index: FakeSearchIndex
    ) -> None:
        fake_index.facet_results = (
            FacetResult(field_code="condition", buckets=(FacetBucketResult(value="NEW", count=3),)),
        )
        outcome = await use_cases.search(_query())
        assert outcome.facets == fake_index.facet_results

    @pytest.mark.asyncio
    async def test_I10_facets_endpoint_returns_the_index_computed_buckets(
        self, use_cases: SearchUseCases, fake_index: FakeSearchIndex
    ) -> None:
        fake_index.facet_results = (
            FacetResult(field_code="rooms", buckets=(FacetBucketResult(value="3", count=7),)),
        )
        results = await use_cases.facets(None)
        assert results == fake_index.facet_results


class TestSuggest:
    @pytest.mark.asyncio
    async def test_I11_returns_up_to_limit_suggestions_from_the_index(
        self, use_cases: SearchUseCases, fake_index: FakeSearchIndex
    ) -> None:
        fake_index.suggestions = (
            SuggestionResult(text="kvartira", type_="QUERY", ref_id=None),
            SuggestionResult(text="kvartira ijaraga", type_="QUERY", ref_id=None),
        )
        results = await use_cases.suggest("kvar", limit=1)
        assert len(results) == 1
