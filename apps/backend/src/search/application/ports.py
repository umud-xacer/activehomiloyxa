"""search/application -- ports (Task P-08). Abstract surface only (typing.Protocol);
`infrastructure/` implements every one of these, never the reverse (Clean Architecture rule 4).
`opensearch-py` types never appear here -- only plain domain/primitive types
(`provider-sdk-confined-to-infrastructure`, tools/importlinter.cfg).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from search.domain import ListingSearchDocument, SearchQuery, SortOption
from shared_kernel import GeoLocation, LocalizedText


@dataclass(frozen=True)
class SearchHitResult:
    """One ranked candidate, as returned by either `SearchIndexPort.search` or
    `FallbackIndexPort.search` -- engine-agnostic, satisfies `search.domain.ranking._Rankable`
    (`is_promoted`) so `apply_promotion_cap` (I-17) runs identically over either source."""

    document: ListingSearchDocument

    @property
    def is_promoted(self) -> bool:
        return self.document.promotion is not None


@dataclass(frozen=True)
class SearchResultPage:
    """A raw page of results from an index/fallback adapter, BEFORE `apply_promotion_cap` runs --
    `application/search_use_cases.py` is the one place the cap (I-17) is applied, uniformly,
    regardless of which port served the request."""

    hits: tuple[SearchHitResult, ...]
    next_cursor: str | None
    total: int | None


@dataclass(frozen=True)
class FacetBucketResult:
    value: str
    count: int


@dataclass(frozen=True)
class FacetResult:
    field_code: str
    buckets: tuple[FacetBucketResult, ...]
    label: LocalizedText | None = None
    """The label an administrator authored for this facet on the `SearchConfiguration`, carried
    through so the interface can show it instead of the raw field code. `None` only when the
    snapshot has no label for the dimension, which the interface renders as the code (its
    previous behaviour for every facet)."""


@dataclass(frozen=True)
class SuggestionResult:
    text: str
    type_: str
    ref_id: UUID | None


@dataclass(frozen=True)
class FacetSpec:
    """One facet dimension to compute buckets for -- sourced from the `SearchConfiguration`
    snapshot (DB Architecture Sec 12: "facet attributes = exactly the facet-eligible field codes
    selected in the SearchConfiguration snapshot -- never arbitrary attributes"), never
    hardcoded."""

    field_code: str


class SearchIndexPort(Protocol):
    """DDD Sec 5.5 `SearchIndexPort` -- index/upsert/delete against OpenSearch, plus the actual
    query execution (full-text/facet/geo/sort/suggest). The ONLY write path to the index
    (P-08's own validation checklist: "no write-path code touches OpenSearch") -- only the
    indexing worker calls `index_document`/`delete_document`; the request path only ever calls
    `search`/`facets`/`suggest`."""

    async def index_document(self, document: ListingSearchDocument) -> None: ...

    async def delete_document(self, listing_id: UUID) -> None: ...

    async def get_document(self, listing_id: UUID) -> ListingSearchDocument | None:
        """Read-your-own-write for the indexing pipeline (e.g. preserving `promotion`/
        `verified_badge` across a content-only re-projection) -- never called from the query
        path."""
        ...

    async def find_listing_ids_by_owner_profile(self, owner_profile_id: UUID) -> tuple[UUID, ...]:
        """Backs the verified-badge fan-out projection (X-03): one `BusinessVerified`/
        `VerificationRejected`/`VerifiedBadgeExpired` event can affect every listing owned by that
        profile, not a single `listing_id`."""
        ...

    async def search(
        self, query: SearchQuery, *, facet_specs: tuple[FacetSpec, ...]
    ) -> SearchResultPage:
        """Raises `search.application.exceptions.SearchIndexUnavailableError` if OpenSearch
        cannot be reached -- the caller (`SearchUseCases`) is responsible for falling back to
        `FallbackIndexPort`, never this method itself."""
        ...

    async def facets(
        self, category_id: UUID | None, facet_specs: tuple[FacetSpec, ...]
    ) -> tuple[FacetResult, ...]: ...

    async def suggest(self, q: str, *, limit: int) -> tuple[SuggestionResult, ...]: ...


class FallbackIndexPort(Protocol):
    """DDD Sec 5.5 `DegradationPolicy [P]` / DB Architecture's trigram+geo fallback (QR-05,
    NFR-REL-002: "if search is unavailable it SHALL fall back to a basic query"). Backed by
    search's OWN `search.listing_fallback_document` table (never `catalog.listing` -- see
    `search/README.md`'s documented resolution of the boundary-rule/Physical-DB-Design conflict),
    populated by the same idempotent indexing use cases that write to OpenSearch."""

    async def upsert_document(self, document: ListingSearchDocument) -> None: ...

    async def delete_document(self, listing_id: UUID) -> None: ...

    async def search(self, query: SearchQuery) -> SearchResultPage:
        """Trigram similarity on `title` + geo bounding-box on `(latitude, longitude)` -- no
        cross-script matching (Physical DB Design's own scope note: "cross-script matching is
        explicitly not a fallback requirement") and no facet bucket computation (undocumented for
        the fallback path; `SearchUseCases.facets` degrades to the configured facet dimensions
        with empty buckets rather than querying this port)."""
        ...


class ConfigurationSnapshotPort(Protocol):
    """Bridges to `configuration`'s `SearchConfiguration` snapshot (`configuration.interfaces`
    only -- the one module search MAY import, SAD Sec 8.1)."""

    async def get_search_configuration(
        self, category_id: UUID | None
    ) -> SearchConfigurationSnapshot: ...


@dataclass(frozen=True)
class SearchConfigurationSnapshot:
    """search's own narrow read shape for `configuration.domain.content.SearchConfigurationContent`
    (Config Framework Sec 3.8/3.9) -- not a `configuration.interfaces` DTO. `sort_options`/
    `default_sort` are validated against the fixed `[P]` `SortOption` vocabulary by the adapter
    that builds this, never by domain/application (DEC-21: configuration selects FROM the fixed
    vocabulary, never extends it)."""

    facet_field_codes: tuple[str, ...]
    sort_options: tuple[SortOption, ...]
    default_sort: SortOption
    promotion_page_cap: int
    facet_labels: tuple[tuple[str, LocalizedText], ...] = ()
    """`(field_code, label)` pairs from the same authored `facets` list `facet_field_codes` is
    built from. A tuple of pairs rather than a mapping so this frozen dataclass stays hashable,
    and last so it can default -- a snapshot built without labels (tests, older callers) still
    constructs and simply falls back to showing field codes."""


class GeocodingPort(Protocol):
    """DDD Sec 5.5 names this port on BC-05 (`GeocodingPort -> Yandex Maps, BRULE-09`). No use
    case in this task calls it: every listing event payload already carries a pre-geocoded
    `GeoLocation` (captured upstream by whoever authored the listing, per FR-MAP-001), so search
    has nothing to geocode on its own read-only projection path. Declared for interface
    completeness/traceability per the Domain Model's own port list; intentionally has zero
    callers in this task (P-08's own scope never asks search to call an external geocoder) --
    flagged in README "Known gaps", not silently dropped."""

    async def geocode(self, address: str) -> GeoLocation: ...
