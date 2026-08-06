"""search -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
operations tagged to this module (contracts/openapi.yaml). Schema only: no aggregate
type is exposed here, no business behaviour, no validation beyond what Pydantic
itself does structurally.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from active_home_shared import CamelModel
from shared_kernel import GeoLocation, LocalizedText, Money


class Facet(CamelModel):
    """OpenAPI `Facet`."""

    field_code: str
    label: LocalizedText
    buckets: list[FacetBuckets]


class FacetBuckets(CamelModel):
    """OpenAPI `FacetBuckets`."""

    value: str | None = None
    count: int | None = None


class SearchResult(CamelModel):
    """Search response — matched listings, facet results, and promotion labelling."""

    items: list[SearchHit]
    facets: list[Facet]
    page: CursorPage
    degraded: bool | None = False
    """True when served from the DB fallback (reduced result set)."""


class SearchHit(CamelModel):
    """OpenAPI `SearchHit`."""

    listing_id: UUID
    title: str
    category_path: str | None = None
    price: Money | None = None
    location: GeoLocation | None = None
    thumbnail_url: str | None = None
    verified_badge: bool | None = None
    promoted: SearchHitPromoted | None = None
    """Present and labelled when the hit is a capped promoted result (BRULE-10)."""
    slug: str | None = None


class SearchHitPromoted(CamelModel):
    """Present and labelled when the hit is a capped promoted result (BRULE-10)."""

    kind: Literal["PREMIUM", "FEATURED", "TOP_PLACEMENT"] | None = None


class CursorPage(CamelModel):
    """Cursor pagination envelope (opaque forward cursor)."""

    items: list[Any]
    page: CursorPagePage


class CursorPagePage(CamelModel):
    """OpenAPI `CursorPagePage`."""

    limit: int
    next_cursor: str | None = None
    """Pass as `cursor` to fetch the next page; null when exhausted."""
    total: int | None = None
    """Present only where cheap to compute; may be null."""


class SearchRequest(CamelModel):
    """Structured search query (also expressible via query parameters on GET /search)."""

    q: str | None = None
    """Free text; matched cross-script (Latin↔Cyrillic)."""
    category_id: UUID | None = None
    owner_profile_id: UUID | None = None
    """Monetization/B2B-directory task: a business profile's own listings (see `search.domain.
    query.SearchQuery.owner_profile_id`'s own docstring)."""
    listing_type: Literal["ADVERTISEMENT", "PRODUCT", "SERVICE"] | None = None
    filters: dict[str, Any] | None = None
    """Facet filters keyed by facet-eligible field code (from the SearchConfiguration snapshot)."""
    price_min: str | None = None
    price_max: str | None = None
    verified_only: bool | None = None
    geo: SearchRequestGeo | None = None
    sort: Literal["RELEVANCE", "RECENCY", "PRICE_ASC", "PRICE_DESC"] | None = "RELEVANCE"


class SearchRequestGeo(CamelModel):
    """OpenAPI `SearchRequestGeo`."""

    center: GeoLocation | None = None
    radius_km: float | None = None


class Suggestion(CamelModel):
    """OpenAPI `Suggestion`.

    `type_` (not `type`, a builtin) needs an explicit `Field(alias=...)`: `CamelModel`'s
    `to_camel` alias generator only reshapes snake_case -> camelCase, it does not know to strip
    a trailing underscore added purely to dodge a Python builtin -- left to the generator alone,
    the wire key comes out as the literal `"type_"`, not OpenAPI's documented `"type"` (confirmed
    via a direct `to_camel("type_")` check; no other DTO field in this codebase uses a trailing
    underscore, so this is the only place this needed catching)."""

    text: str
    type_: Literal["QUERY", "CATEGORY", "LISTING"] | None = Field(default=None, alias="type")
    ref_id: UUID | None = None
