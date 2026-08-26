"""`search.infrastructure.persistence.repository` -- pure-function tests for `_price_filter` (the
Postgres-fallback sibling of `opensearch_index._price_filter`). Compiled to a literal-bind SQL
string so the currency-aware branching can be asserted without a live database -- the adapter
class itself (`SqlalchemyFallbackIndexRepository`, the I/O-performing type) is exercised only by
the real-Postgres integration tier (`tests/search/integration/test_repository_live.py`)."""

from __future__ import annotations

from decimal import Decimal

from search.domain import SearchQuery, SortOption
from search.infrastructure.persistence.repository import _price_filter


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


def _compiled(clause: object) -> str:
    return str(clause.compile(compile_kwargs={"literal_binds": True}))  # type: ignore[union-attr]


class TestPriceFilter:
    def test_no_price_bounds_means_no_filter_at_all(self) -> None:
        assert _price_filter(_query()) is None

    def test_without_a_rate_builds_the_old_flat_currency_blind_range(self) -> None:
        clause = _price_filter(_query(price_min=Decimal("1000"), price_max=Decimal("5000")))
        sql = _compiled(clause)
        assert "price_currency" not in sql
        assert "price_amount >= 1000" in sql
        assert "price_amount <= 5000" in sql

    def test_with_a_rate_builds_an_or_of_a_uzs_bucket_and_a_usd_bucket(self) -> None:
        clause = _price_filter(
            _query(
                price_min=Decimal("1000000"),
                price_max=Decimal("5000000"),
                fx_usd_to_uzs=Decimal("12500"),
            )
        )
        sql = _compiled(clause)
        assert "price_currency = 'UZS'" in sql
        assert "price_currency = 'USD'" in sql
        # UZS bucket compares against the bounds directly...
        assert "price_amount >= 1000000" in sql
        assert "price_amount <= 5000000" in sql
        # ...the USD bucket against the bounds divided by the rate (1,000,000/12,500=80,
        # 5,000,000/12,500=400) -- a $100 listing is well inside this range even though 100 is
        # nowhere near the raw 1,000,000-5,000,000 UZS bounds it was typed against.
        assert "price_amount >= 80" in sql
        assert "price_amount <= 400" in sql

    def test_a_zero_or_negative_rate_falls_back_to_the_currency_blind_range(self) -> None:
        clause = _price_filter(
            _query(price_min=Decimal("1000"), price_max=None, fx_usd_to_uzs=Decimal("0"))
        )
        sql = _compiled(clause)
        assert "price_currency" not in sql
        assert "price_amount >= 1000" in sql
