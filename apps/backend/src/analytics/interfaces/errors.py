"""Registers analytics' typed domain/application exceptions onto the shared
`backbone.errors.ExceptionMapper` (the same registry `billing.interfaces.errors`/`ads.
interfaces.errors` extend). Called once from the composition root (`apps/backend/src/main.py`).

`UnknownMetricKeyError`/`ImmutableFactMutationError` are domain-internal (I-23/I-22 guards) --
they never reach an HTTP boundary in v1 (nothing here exposes a metric/audit WRITE endpoint), so
only `UnknownReportError` (the one user-facing 4xx analytics can actually produce) is mapped.
"""

from __future__ import annotations

from analytics.application.exceptions import UnknownReportError
from backbone.errors import ExceptionMapper, simple_problem_builder


def register_analytics_exception_mappings(mapper: ExceptionMapper) -> None:
    mapper.register(
        UnknownReportError,
        simple_problem_builder(
            status=422, code="VALIDATION_FAILED", title="Unknown report dataset"
        ),
    )
