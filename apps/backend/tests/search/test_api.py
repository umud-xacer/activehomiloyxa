"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real OpenSearch/Postgres/configuration providers swapped for in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production. Covers the four
search-tagged OpenAPI operations (`searchListingsGet`, `searchListingsPost`, `getFacets`,
`suggest`), all public (`security: []`, no `ActingUser` override needed). Mirrors
`apps/backend/tests/catalog/test_api.py`'s pattern exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import create_app
from search.application.search_use_cases import SearchUseCases
from search.domain import ListingType, PromotionKind, PromotionMarker
from search.domain.search_document import ListingSearchDocument
from search.interfaces.di import get_search_use_cases

from .conftest import FakeConfigurationSnapshotPort, FakeFallbackIndex, FakeSearchIndex

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.fixture
def client(
    fake_index: FakeSearchIndex,
    fake_fallback: FakeFallbackIndex,
    fake_configuration: FakeConfigurationSnapshotPort,
) -> Iterator[TestClient]:
    def _search_use_cases() -> SearchUseCases:
        return SearchUseCases(
            index=fake_index, fallback=fake_fallback, configuration=fake_configuration
        )

    app = create_app()
    app.dependency_overrides[get_search_use_cases] = _search_use_cases

    with TestClient(
        app, base_url="https://testserver", raise_server_exceptions=False
    ) as test_client:
        yield test_client


def _seed_document(
    index: FakeSearchIndex | FakeFallbackIndex, **overrides: object
) -> ListingSearchDocument:
    kwargs: dict[str, object] = {
        "listing_id": uuid4(),
        "owner_profile_id": None,
        "title": "Kvartira sotiladi",
        "description": None,
        "category_id": uuid4(),
        "category_path": "/real-estate/apartments",
        "listing_type": ListingType.ADVERTISEMENT,
        "attributes": {},
        "price": None,
        "location": None,
        "verified_badge": False,
        "publicly_visible": True,
        "slug": "kvartira-sotiladi",
        "published_at": _NOW,
        "updated_at": _NOW,
    }
    kwargs.update(overrides)
    document = ListingSearchDocument.project(**kwargs)  # type: ignore[arg-type]
    index.documents[document.listing_id] = document
    return document


class TestSearchListingsGet:
    def test_I01_returns_200_with_an_empty_result_when_no_documents_are_indexed(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/v1/search")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["degraded"] is False

    def test_I02_returns_a_matching_listing(
        self, client: TestClient, fake_index: FakeSearchIndex
    ) -> None:
        document = _seed_document(fake_index, title="Kvartira")
        response = client.get("/api/v1/search", params={"q": "kvartira"})
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["listingId"] == str(document.listing_id)

    def test_I03_cross_script_query_matches_latin_indexed_content(
        self, client: TestClient, fake_index: FakeSearchIndex
    ) -> None:
        _seed_document(fake_index, title="Kvartira")
        response = client.get("/api/v1/search", params={"q": "квартира"})
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_I04_deep_object_filters_are_parsed_off_raw_query_params(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/api/v1/search", params=[("filters[condition]", "NEW"), ("q", "kvartira")]
        )
        assert response.status_code == 200

    def test_I05_limit_above_the_maximum_is_clamped_not_rejected(self, client: TestClient) -> None:
        response = client.get("/api/v1/search", params={"limit": 500})
        assert response.status_code == 200
        assert response.json()["page"]["page"]["limit"] == 100

    def test_I06_a_promoted_hit_carries_its_promotion_label(
        self, client: TestClient, fake_index: FakeSearchIndex
    ) -> None:
        document = _seed_document(fake_index, title="Featured listing")
        promoted = document.with_promotion(
            promotion=PromotionMarker(
                kind=PromotionKind.FEATURED, valid_until=None, entitlement_id=uuid4()
            ),
            updated_at=_NOW,
        )
        fake_index.documents[document.listing_id] = promoted
        response = client.get("/api/v1/search", params={"q": "featured"})
        items = response.json()["items"]
        assert items[0]["promoted"]["kind"] == "FEATURED"

    def test_I07_falls_back_to_postgres_and_reports_degraded_true_when_the_index_is_unavailable(
        self, client: TestClient, fake_index: FakeSearchIndex, fake_fallback: FakeFallbackIndex
    ) -> None:
        fake_index.unavailable = True
        document = _seed_document(fake_fallback, title="Kvartira")
        response = client.get("/api/v1/search", params={"q": "kvartira"})
        assert response.status_code == 200
        body = response.json()
        assert body["degraded"] is True
        assert len(body["items"]) == 1
        assert body["items"][0]["listingId"] == str(document.listing_id)


class TestSearchListingsPost:
    def test_I08_accepts_a_structured_search_request_body(
        self, client: TestClient, fake_index: FakeSearchIndex
    ) -> None:
        _seed_document(fake_index, title="Kvartira")
        response = client.post("/api/v1/search", json={"q": "kvartira", "sort": "RECENCY"})
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_I09_geo_radius_body_is_accepted(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/search",
            json={"geo": {"center": {"latitude": 41.3, "longitude": 69.2}, "radiusKm": 5.0}},
        )
        assert response.status_code == 200


class TestGetFacets:
    def test_I10_returns_the_bucket_data_the_index_computed_for_the_configured_fields(
        self, client: TestClient, fake_index: FakeSearchIndex
    ) -> None:
        from search.application.ports import FacetBucketResult, FacetResult

        fake_index.facet_results = (
            FacetResult(field_code="condition", buckets=(FacetBucketResult(value="NEW", count=3),)),
            FacetResult(field_code="rooms", buckets=()),
        )
        response = client.get("/api/v1/search/facets")
        assert response.status_code == 200
        field_codes = {facet["fieldCode"] for facet in response.json()}
        assert field_codes == {"condition", "rooms"}

    def test_I11_degrades_to_empty_buckets_when_the_index_is_unavailable(
        self, client: TestClient, fake_index: FakeSearchIndex
    ) -> None:
        fake_index.unavailable = True
        response = client.get("/api/v1/search/facets")
        assert response.status_code == 200
        assert all(facet["buckets"] == [] for facet in response.json())


class TestSuggest:
    def test_I12_returns_suggestions_with_the_correct_wire_key_type_not_type(
        self, client: TestClient, fake_index: FakeSearchIndex
    ) -> None:
        from search.application.ports import SuggestionResult

        fake_index.suggestions = (SuggestionResult(text="kvartira", type_="QUERY", ref_id=None),)
        response = client.get("/api/v1/search/suggest", params={"q": "kvar"})
        assert response.status_code == 200
        body = response.json()
        assert body[0]["type"] == "QUERY"
        assert "type_" not in body[0]

    def test_I13_limit_above_ten_is_clamped(
        self, client: TestClient, fake_index: FakeSearchIndex
    ) -> None:
        from search.application.ports import SuggestionResult

        fake_index.suggestions = tuple(
            SuggestionResult(text=f"kvartira {i}", type_="QUERY", ref_id=None) for i in range(20)
        )
        response = client.get("/api/v1/search/suggest", params={"q": "kvar", "limit": 50})
        assert response.status_code == 200
        assert len(response.json()) == 10
