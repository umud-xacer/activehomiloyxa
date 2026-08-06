"""analytics/application -- application-layer typed exceptions."""

from __future__ import annotations


class AnalyticsApplicationError(Exception):
    """Base for every analytics application-layer error."""


class UnknownReportError(AnalyticsApplicationError):
    """Raised for a `report` query value outside the fixed v1 report set (FR-ADMIN-005,
    BRULE-20) -- the OpenAPI `report` enum is the closed vocabulary; this mirrors that closure at
    the application layer rather than trusting FastAPI's own enum validation alone."""

    def __init__(self, report: str) -> None:
        self.report = report
        super().__init__(f"{report!r} is not one of the fixed v1 report datasets")
