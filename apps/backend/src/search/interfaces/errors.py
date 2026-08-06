"""Registers search's typed application exceptions onto the shared `backbone.errors.
ExceptionMapper` (the same registry `identity.interfaces.errors`/`catalog.interfaces.errors`
extend). Called once from the composition root (`apps/backend/src/main.py`).

Both mappings below use `DEPENDENCY_DEGRADED`/503, the same status/code catalog's own
`CategoryFormUnavailableError` mapping already established for "a required collaborator has no
usable data right now" -- exactly the shape `contracts/openapi.yaml`'s `ServiceDegraded` response
(declared on both `GET /search` and `POST /search`) describes. `SearchIndexUnavailableError` is
registered defensively: `SearchUseCases.search`/`facets`/`suggest` already catch it internally
(`DegradationPolicy [P]`, NFR-REL-002) and it should never reach this mapper in practice -- this
mapping only guards a future call site that forgets to."""

from __future__ import annotations

from backbone.errors import ExceptionMapper, simple_problem_builder
from search.application.exceptions import (
    NoSearchConfigurationPublishedError,
    SearchIndexUnavailableError,
)


def register_search_exception_mappings(mapper: ExceptionMapper) -> None:
    mapper.register(
        NoSearchConfigurationPublishedError,
        simple_problem_builder(
            status=503,
            code="DEPENDENCY_DEGRADED",
            title="No SearchConfiguration has been published for this scope",
        ),
    )
    mapper.register(
        SearchIndexUnavailableError,
        simple_problem_builder(
            status=503, code="DEPENDENCY_DEGRADED", title="The search index is unavailable"
        ),
    )
