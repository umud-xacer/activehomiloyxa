"""FastAPI routers implementing exactly the four search-tagged OpenAPI operations
(`contracts/openapi.yaml`) -- `searchListingsGet`, `searchListingsPost`, `getFacets`, `suggest`.
Thin translation only: query-params/body -> `search.domain.SearchQuery` -> `SearchUseCases` call
-> already-frozen `interfaces/dto.py` DTO. All business logic (index-vs-fallback degradation,
promotion capping) lives in `application`; this module owns none. Mirrors `catalog.interfaces.
routers`'s pattern exactly.

Every operation here declares `security: []` in `contracts/openapi.yaml` -- none take an
`ActingUser` dependency (`search/interfaces/di.py` declares none).

`filters` (`GET /search`'s `style: deepObject, explode: true` query parameter, e.g.
`filters[condition]=NEW`) is not a shape FastAPI parses from a single named parameter -- it is
read directly off the raw `Request.query_params` by `_parse_deep_object_filters`, the same
approach OpenAPI's own `deepObject` style requires of any server that isn't generating parsing
code from the spec.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from search.application import (
    FacetResult,
    SearchHitResult,
    SearchOutcome,
    SearchUseCases,
    SuggestionResult,
)
from search.domain import GeoFilter, ListingType, SearchQuery, SortOption
from search.interfaces.di import get_search_use_cases
from search.interfaces.dto import (
    CursorPage,
    CursorPagePage,
    Facet,
    FacetBuckets,
    SearchHit,
    SearchHitPromoted,
    SearchRequest,
    SearchResult,
    Suggestion,
)
from shared_kernel import GeoLocation, LocalizedText

search_router = APIRouter(tags=["Search"])

_FILTERS_PREFIX = "filters["


def _parse_deep_object_filters(request: Request) -> dict[str, str]:
    filters: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key.startswith(_FILTERS_PREFIX) and key.endswith("]"):
            field_code = key[len(_FILTERS_PREFIX) : -1]
            if field_code:
                filters[field_code] = value
    return filters


def _clamp_limit(limit: int | None) -> int:
    """OpenAPI `Limit` parameter: "Values above the maximum are clamped, not rejected." (1-100)."""
    return min(max(limit or 20, 1), 100)


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _to_search_hit(hit: SearchHitResult) -> SearchHit:
    doc = hit.document
    return SearchHit(
        listing_id=doc.listing_id,
        title=doc.title,
        category_path=doc.category_path,
        price=doc.price,
        location=doc.location,
        # `thumbnailUrl` has been in the frozen contract since P-01 but was hardcoded `None` here
        # while the read model carried no image field at all, so every result card on the home
        # and search pages rendered a placeholder no matter how many images the listing had.
        thumbnail_url=doc.primary_image_thumbnail_url,
        verified_badge=doc.verified_badge,
        promoted=(SearchHitPromoted(kind=doc.promotion.kind.value) if doc.promotion else None),
        slug=doc.slug,
    )


def _field_code_label(field_code: str) -> LocalizedText:
    """Last-resort `Facet.label` when the `SearchConfiguration` carries none for this dimension.

    Echoing the field code is never a guessed translation and never blank -- but it is also not
    something to show an end user, which is why the authored label is preferred wherever one
    exists. `SearchConfigurationSnapshot` now carries the labels an administrator wrote beside
    each facet, so this fires only for a dimension configured without one."""
    return LocalizedText(uz_latn=field_code)


def _to_facet_dto(result: FacetResult) -> Facet:
    return Facet(
        field_code=result.field_code,
        label=result.label or _field_code_label(result.field_code),
        buckets=[FacetBuckets(value=b.value, count=b.count) for b in result.buckets],
    )


def _to_suggestion_dto(result: SuggestionResult) -> Suggestion:
    return Suggestion(text=result.text, type_=result.type_, ref_id=result.ref_id)  # type: ignore[arg-type]


def _to_search_result(outcome: SearchOutcome, *, limit: int) -> SearchResult:
    return SearchResult(
        items=[_to_search_hit(hit) for hit in outcome.hits],
        facets=[_to_facet_dto(f) for f in outcome.facets],
        page=CursorPage(
            items=[],
            page=CursorPagePage(limit=limit, next_cursor=outcome.next_cursor, total=outcome.total),
        ),
        degraded=outcome.degraded,
    )


@search_router.get("/search", operation_id="searchListingsGet")
async def search_listings_get(
    request: Request,
    q: str | None = None,
    categoryId: UUID | None = None,
    categoryPathPrefix: str | None = None,
    ownerProfileId: UUID | None = None,
    listingType: Literal["ADVERTISEMENT", "PRODUCT", "SERVICE"] | None = None,
    priceMin: str | None = None,
    priceMax: str | None = None,
    verifiedOnly: bool | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radiusKm: float | None = None,
    sort: Literal["RELEVANCE", "RECENCY", "PRICE_ASC", "PRICE_DESC"] | None = "RELEVANCE",
    cursor: str | None = None,
    limit: int | None = 20,
    use_cases: SearchUseCases = Depends(get_search_use_cases),
) -> SearchResult:
    geo = (
        GeoFilter(center=GeoLocation(latitude=lat, longitude=lng), radius_km=radiusKm)
        if lat is not None and lng is not None and radiusKm is not None
        else None
    )
    page_limit = _clamp_limit(limit)
    query = SearchQuery(
        q=q,
        category_id=categoryId,
        owner_profile_id=ownerProfileId,
        listing_type=ListingType(listingType) if listingType else None,
        filters=_parse_deep_object_filters(request),
        price_min=_parse_decimal(priceMin),
        price_max=_parse_decimal(priceMax),
        verified_only=bool(verifiedOnly),
        geo=geo,
        sort=SortOption(sort) if sort else SortOption.RELEVANCE,
        cursor=cursor,
        limit=page_limit,
        category_path_prefix=categoryPathPrefix,
    )
    outcome = await use_cases.search(query)
    return _to_search_result(outcome, limit=page_limit)


@search_router.post("/search", operation_id="searchListingsPost")
async def search_listings_post(
    body: SearchRequest,
    cursor: str | None = None,
    limit: int | None = 20,
    use_cases: SearchUseCases = Depends(get_search_use_cases),
) -> SearchResult:
    geo = (
        GeoFilter(center=body.geo.center, radius_km=body.geo.radius_km)
        if body.geo is not None and body.geo.center is not None and body.geo.radius_km is not None
        else None
    )
    page_limit = _clamp_limit(limit)
    query = SearchQuery(
        q=body.q,
        category_id=body.category_id,
        owner_profile_id=body.owner_profile_id,
        listing_type=ListingType(body.listing_type) if body.listing_type else None,
        filters={k: str(v) for k, v in (body.filters or {}).items()},
        price_min=_parse_decimal(body.price_min),
        price_max=_parse_decimal(body.price_max),
        verified_only=bool(body.verified_only),
        geo=geo,
        sort=SortOption(body.sort) if body.sort else SortOption.RELEVANCE,
        cursor=cursor,
        limit=page_limit,
        category_path_prefix=body.category_path_prefix,
    )
    outcome = await use_cases.search(query)
    return _to_search_result(outcome, limit=page_limit)


@search_router.get("/search/facets", operation_id="getFacets")
async def get_facets(
    categoryId: UUID | None = None,
    use_cases: SearchUseCases = Depends(get_search_use_cases),
) -> list[Facet]:
    results = await use_cases.facets(categoryId)
    return [_to_facet_dto(f) for f in results]


@search_router.get("/search/suggest", operation_id="suggest")
async def suggest(
    q: str,
    limit: int | None = 5,
    use_cases: SearchUseCases = Depends(get_search_use_cases),
) -> list[Suggestion]:
    results = await use_cases.suggest(q, limit=min(max(limit or 5, 1), 10))
    return [_to_suggestion_dto(r) for r in results]
