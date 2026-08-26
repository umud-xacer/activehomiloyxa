"""`search.infrastructure.opensearch_index` -- pure-function tests for `_document_to_source`/
`_source_to_document` (the OpenSearch wire-shape round trip) and `_build_query_body` (the query
DSL construction: cross-script matching, geo radius, facet filters). None of this needs a live
OpenSearch cluster -- `OpenSearchIndexAdapter` itself (the I/O-performing class) is exercised only
by the (skip-without-OPENSEARCH_HOST) integration tier."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from search.domain import (
    GeoFilter,
    ListingType,
    PromotionKind,
    PromotionMarker,
    SearchQuery,
    SortOption,
)
from search.domain.search_document import ListingSearchDocument
from search.infrastructure.opensearch_index import (
    _build_query_body,
    _document_to_source,
    _price_filter,
    _source_to_document,
)
from shared_kernel import GeoLocation, Money

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _document(**overrides: object) -> ListingSearchDocument:
    kwargs: dict[str, object] = {
        "listing_id": uuid4(),
        "owner_profile_id": uuid4(),
        "title": "Kvartira",
        "description": "3-xonali",
        "category_id": uuid4(),
        "category_path": "/real-estate",
        "listing_type": ListingType.ADVERTISEMENT,
        "attributes": {"rooms": "3"},
        "price": Money(amount=Decimal("1500.00"), currency="USD"),
        "location": GeoLocation(latitude=41.3, longitude=69.2),
        "verified_badge": True,
        "publicly_visible": True,
        "slug": "kvartira",
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


class TestDocumentSourceRoundTrip:
    def test_I01_round_trips_a_plain_document(self) -> None:
        document = _document()
        restored = _source_to_document(_document_to_source(document))
        assert restored == document

    def test_I02_round_trips_a_promoted_documents_entitlement_id(self) -> None:
        # regression test: `_document_to_source` used to omit `promotion_entitlement_id` entirely,
        # so `_source_to_document` always fell back to `UUID(int=0)` on read -- silently losing
        # the real entitlement id for every promoted document served from OpenSearch.
        promotion = PromotionMarker(
            kind=PromotionKind.PREMIUM, valid_until=_NOW, entitlement_id=uuid4()
        )
        document = _document().with_promotion(promotion=promotion, updated_at=_NOW)
        restored = _source_to_document(_document_to_source(document))
        assert restored.promotion is not None
        assert restored.promotion.entitlement_id == promotion.entitlement_id
        assert restored.promotion.entitlement_id != uuid4()

    def test_I03_round_trips_a_document_with_no_price_location_or_promotion(self) -> None:
        document = _document(price=None, location=None)
        restored = _source_to_document(_document_to_source(document))
        assert restored.price is None
        assert restored.location is None
        assert restored.promotion is None


class TestBuildQueryBody:
    def test_I04_always_filters_to_publicly_visible_documents(self) -> None:
        body = _build_query_body(_query(), facet_specs=())
        filters = body["query"]["function_score"]["query"]["bool"]["filter"]
        assert {"term": {"publicly_visible": True}} in filters

    def test_I05_free_text_query_matches_both_normalized_script_fields(self) -> None:
        body = _build_query_body(_query(q="kvartira"), facet_specs=())
        should_clauses = body["query"]["function_score"]["query"]["bool"]["must"][0]["bool"][
            "should"
        ]
        matched_fields = {field for clause in should_clauses for field in clause.get("match", {})}
        assert "title_normalized_latin" in matched_fields
        assert "title_normalized_cyrillic" in matched_fields

    def test_I06_geo_filter_becomes_a_geo_distance_clause(self) -> None:
        geo = GeoFilter(center=GeoLocation(latitude=41.3, longitude=69.2), radius_km=5.0)
        body = _build_query_body(_query(geo=geo), facet_specs=())
        filters = body["query"]["function_score"]["query"]["bool"]["filter"]
        geo_clauses = [f for f in filters if "geo_distance" in f]
        assert len(geo_clauses) == 1
        assert geo_clauses[0]["geo_distance"]["distance"] == "5.0km"

    def test_I07_sort_option_selects_the_documented_sort_field(self) -> None:
        body = _build_query_body(_query(sort=SortOption.PRICE_ASC), facet_specs=())
        assert body["sort"] == [{"price_amount": {"order": "asc", "missing": "_last"}}]

    def test_I08_promoted_documents_get_a_function_score_boost_not_a_hard_reorder(self) -> None:
        body = _build_query_body(_query(), facet_specs=())
        functions = body["query"]["function_score"]["functions"]
        assert functions == [{"filter": {"exists": {"field": "promotion_kind"}}, "weight": 1.5}]


class TestPriceFilter:
    def test_I09_no_price_bounds_means_no_filter_at_all(self) -> None:
        assert _price_filter(_query()) is None

    def test_I10_without_a_rate_builds_the_old_flat_currency_blind_range(self) -> None:
        clause = _price_filter(_query(price_min=Decimal("1000"), price_max=Decimal("5000")))
        assert clause == {"range": {"price_amount": {"gte": 1000.0, "lte": 5000.0}}}

    def test_I11_with_a_rate_builds_an_or_of_a_uzs_bucket_and_a_usd_bucket(self) -> None:
        clause = _price_filter(
            _query(
                price_min=Decimal("1000000"),
                price_max=Decimal("5000000"),
                fx_usd_to_uzs=Decimal("12500"),
            )
        )
        assert clause is not None
        should = clause["bool"]["should"]
        assert clause["bool"]["minimum_should_match"] == 1
        assert len(should) == 2
        uzs_clause = next(
            c for c in should if {"term": {"price_currency": "UZS"}} in c["bool"]["filter"]
        )
        usd_clause = next(
            c for c in should if {"term": {"price_currency": "USD"}} in c["bool"]["filter"]
        )
        uzs_range = next(
            f["range"]["price_amount"] for f in uzs_clause["bool"]["filter"] if "range" in f
        )
        usd_range = next(
            f["range"]["price_amount"] for f in usd_clause["bool"]["filter"] if "range" in f
        )
        # a UZS-priced listing is compared against the bounds directly...
        assert uzs_range == {"gte": 1000000.0, "lte": 5000000.0}
        # ...while a USD-priced listing is compared against the bounds divided by the rate, so a
        # $100 listing (well within the 80-400 range) is included even though 100 is nowhere near
        # the 1,000,000-5,000,000 UZS bounds it was typed against.
        assert usd_range == {"gte": 80.0, "lte": 400.0}

    def test_I12_a_zero_or_negative_rate_falls_back_to_the_currency_blind_range(self) -> None:
        # a caller-supplied rate of 0 (or negative, never legitimate) must not divide-by-zero --
        # treated the same as "no rate supplied" rather than raising.
        clause = _price_filter(
            _query(price_min=Decimal("1000"), price_max=None, fx_usd_to_uzs=Decimal("0"))
        )
        assert clause == {"range": {"price_amount": {"gte": 1000.0}}}

    def test_I13_build_query_body_includes_the_dual_currency_filter_when_a_rate_is_set(
        self,
    ) -> None:
        body = _build_query_body(
            _query(price_min=Decimal("100"), fx_usd_to_uzs=Decimal("12500")), facet_specs=()
        )
        filters = body["query"]["function_score"]["query"]["bool"]["filter"]
        price_clauses = [f for f in filters if "bool" in f and "should" in f.get("bool", {})]
        assert len(price_clauses) == 1
