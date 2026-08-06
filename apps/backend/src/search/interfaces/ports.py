"""search -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from search.interfaces.dto import (
    Facet,
    SearchRequest,
    SearchResult,
    Suggestion,
)


class SearchQueryPort(Protocol):
    """Derived from OpenAPI operations: `getFacets`, `searchListingsGet`, `searchListingsPost`, `suggest`."""

    async def get_facets(self, category_id: UUID | None = None) -> list[Facet]:
        """`GET /search/facets` (operationId `getFacets`). Get available facets for a scope"""
        ...

    async def search_listings_get(
        self,
        q: str | None = None,
        category_id: UUID | None = None,
        listing_type: Literal["ADVERTISEMENT", "PRODUCT", "SERVICE"] | None = None,
        filters: dict[str, Any] | None = None,
        price_min: str | None = None,
        price_max: str | None = None,
        verified_only: bool | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
        sort: Literal["RELEVANCE", "RECENCY", "PRICE_ASC", "PRICE_DESC"] | None = "RELEVANCE",
        cursor: str | None = None,
        limit: int | None = 20,
    ) -> SearchResult:
        """`GET /search` (operationId `searchListingsGet`). Search listings (query parameters)"""
        ...

    async def search_listings_post(
        self, body: SearchRequest, cursor: str | None = None, limit: int | None = 20
    ) -> SearchResult:
        """`POST /search` (operationId `searchListingsPost`). Search listings (structured body)"""
        ...

    async def suggest(self, q: str, limit: int | None = 5) -> list[Suggestion]:
        """`GET /search/suggest` (operationId `suggest`). Autocomplete / suggestions"""
        ...
