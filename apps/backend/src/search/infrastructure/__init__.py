"""search/infrastructure -- the OpenSearch adapter, Postgres fallback/checkpoint repositories,
the `SearchConfiguration` bridge to `configuration`, idempotent event-projection handlers, and the
background indexing worker (Task P-08). Never imported by `search.interfaces`/`application`/
`domain` -- only the composition root (outside every module's package tree) wires these concrete
classes behind the ports `application/` declares."""

from __future__ import annotations

from search.infrastructure.configuration_adapter import ConfigurationSearchConfigurationAdapter
from search.infrastructure.event_projection import (
    dispatch_search_event,
    make_search_event_handler,
)
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from search.infrastructure.persistence import (
    ListingFallbackDocumentRow,
    ProcessedEventRow,
    ProjectionCheckpointRow,
    SearchBase,
    SqlalchemyFallbackIndexRepository,
    SqlalchemyProjectionCheckpointRepository,
)
from search.infrastructure.worker import SearchIndexingWorker

__all__ = [
    "ConfigurationSearchConfigurationAdapter",
    "ListingFallbackDocumentRow",
    "OpenSearchIndexAdapter",
    "ProcessedEventRow",
    "ProjectionCheckpointRow",
    "SearchBase",
    "SearchIndexingWorker",
    "SqlalchemyFallbackIndexRepository",
    "SqlalchemyProjectionCheckpointRepository",
    "dispatch_search_event",
    "make_search_event_handler",
]
