"""search/application -- `SearchUseCases` (Task P-08): `search`/`facets`/`suggest`, backing the
four public search-tagged OpenAPI operations (`getFacets`, `searchListingsGet`/
`searchListingsPost`, `suggest`). `DegradationPolicy [P]` (NFR-REL-002) and `PromotionCapAndLabel
Policy [P]` (I-17) both run here, uniformly, regardless of which port ultimately served the
request -- this is the one place either invariant is enforced, never duplicated in an adapter.

Returns application-level result types (`SearchOutcome`/`FacetResult`/`SuggestionResult`), never
`search.interfaces.dto` types: `layers-search` (tools/importlinter.cfg) forbids `search.
application` importing `search.interfaces` (Clean Architecture -- application must not know its
callers' wire shape). `search/interfaces/routers.py` does the DTO translation, mirroring
`catalog.interfaces.routers`'s own `_listing_to_dto`-in-the-router pattern exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from search.application.exceptions import SearchIndexUnavailableError
from search.application.ports import (
    ConfigurationSnapshotPort,
    FacetResult,
    FacetSpec,
    FallbackIndexPort,
    SearchHitResult,
    SearchIndexPort,
    SuggestionResult,
)
from search.domain import SearchQuery, apply_promotion_cap


@dataclass(frozen=True)
class SearchOutcome:
    """`SearchUseCases.search`'s return shape -- capped/ranked hits plus paging/degradation state,
    already past `apply_promotion_cap` (I-17). `search/interfaces/routers.py` translates this into
    the OpenAPI `SearchResult` DTO; nothing below `interfaces/` knows that shape exists."""

    hits: list[SearchHitResult]
    facets: tuple[FacetResult, ...]
    next_cursor: str | None
    total: int | None
    degraded: bool


class SearchUseCases:
    def __init__(
        self,
        *,
        index: SearchIndexPort,
        fallback: FallbackIndexPort,
        configuration: ConfigurationSnapshotPort,
    ) -> None:
        self._index = index
        self._fallback = fallback
        self._configuration = configuration

    async def search(self, query: SearchQuery) -> SearchOutcome:
        """FR-SRCH-001/002/003/004, FR-MAP-003. Tries the OpenSearch-backed index first; on
        `SearchIndexUnavailableError`, degrades to the PostgreSQL trigram/geo fallback
        (`DegradationPolicy [P]`, NFR-REL-002) rather than failing the request -- `degraded=True`
        signals this to the caller (`SearchResult.degraded`, OpenAPI's own documented field)."""
        snapshot = await self._configuration.get_search_configuration(query.category_id)
        facet_specs = tuple(FacetSpec(field_code=code) for code in snapshot.facet_field_codes)
        labels = dict(snapshot.facet_labels)

        degraded = False
        try:
            page = await self._index.search(query, facet_specs=facet_specs)
            facets = await self._index.facets(query.category_id, facet_specs)
        except SearchIndexUnavailableError:
            degraded = True
            page = await self._fallback.search(query)
            # DB Architecture Sec 12: bucket counts are undocumented for the fallback path --
            # only facet DIMENSIONS (from configuration) survive degradation, never their counts.
            facets = tuple(
                FacetResult(
                    field_code=spec.field_code, buckets=(), label=labels.get(spec.field_code)
                )
                for spec in facet_specs
            )

        # The index knows bucket counts but nothing about authored labels, so they are attached
        # here rather than pushed down into the index port.
        facets = tuple(
            replace(facet, label=facet.label or labels.get(facet.field_code)) for facet in facets
        )

        capped_hits = apply_promotion_cap(list(page.hits), cap=snapshot.promotion_page_cap)

        return SearchOutcome(
            hits=capped_hits,
            facets=facets,
            next_cursor=page.next_cursor,
            total=page.total,
            degraded=degraded,
        )

    async def facets(self, category_id: UUID | None) -> tuple[FacetResult, ...]:
        """FR-SRCH-002. Facet DIMENSIONS (field_code/label) always come from the
        `SearchConfiguration` snapshot, never OpenSearch -- only their bucket VALUE/COUNT pairs
        need the index, so a facets-only request degrades to empty buckets (never an error) if
        the index is unreachable."""
        snapshot = await self._configuration.get_search_configuration(category_id)
        facet_specs = tuple(FacetSpec(field_code=code) for code in snapshot.facet_field_codes)
        labels = dict(snapshot.facet_labels)
        try:
            results = await self._index.facets(category_id, facet_specs)
        except SearchIndexUnavailableError:
            results = tuple(
                FacetResult(field_code=spec.field_code, buckets=()) for spec in facet_specs
            )
        # This method's own contract is that the DIMENSION -- field code AND label -- comes from
        # the snapshot, never the index. The index supplies only bucket values and counts, so the
        # authored label is attached here on both paths.
        return tuple(
            replace(facet, label=facet.label or labels.get(facet.field_code)) for facet in results
        )

    async def suggest(self, q: str, *, limit: int) -> tuple[SuggestionResult, ...]:
        """`/search/suggest` -- no backing SRS FR (see README "Known gaps"); implemented purely
        from the frozen OpenAPI contract over indexed listing titles. No fallback tier exists for
        suggestions (Physical DB Design documents trigram/geo fallback only, never a suggest
        fallback) -- an unavailable index simply returns an empty suggestion list rather than an
        error, since autocomplete degrading to "no suggestions" is a harmless UX reduction, not a
        failed request."""
        try:
            return await self._index.suggest(q, limit=limit)
        except SearchIndexUnavailableError:
            return ()
