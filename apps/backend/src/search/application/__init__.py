"""search/application -- use cases + ports (Task P-08). Depends only on `search.domain` and
`shared_kernel` -- never `search.interfaces` (`layers-search`, tools/importlinter.cfg): DTO
translation lives in `search.interfaces.routers` instead, which converts the `SearchOutcome`/
`FacetResult`/`SuggestionResult` types this package returns into wire DTOs."""

from __future__ import annotations

from search.application.exceptions import (
    NoSearchConfigurationPublishedError,
    SearchApplicationError,
    SearchIndexUnavailableError,
)
from search.application.indexing_use_cases import IndexingUseCases
from search.application.ports import (
    ConfigurationSnapshotPort,
    FacetBucketResult,
    FacetResult,
    FacetSpec,
    FallbackIndexPort,
    GeocodingPort,
    SearchConfigurationSnapshot,
    SearchHitResult,
    SearchIndexPort,
    SearchResultPage,
    SuggestionResult,
)
from search.application.search_use_cases import SearchOutcome, SearchUseCases

__all__ = [
    "ConfigurationSnapshotPort",
    "FacetBucketResult",
    "FacetResult",
    "FacetSpec",
    "FallbackIndexPort",
    "GeocodingPort",
    "IndexingUseCases",
    "NoSearchConfigurationPublishedError",
    "SearchApplicationError",
    "SearchConfigurationSnapshot",
    "SearchHitResult",
    "SearchIndexPort",
    "SearchIndexUnavailableError",
    "SearchOutcome",
    "SearchResultPage",
    "SearchUseCases",
    "SuggestionResult",
]
