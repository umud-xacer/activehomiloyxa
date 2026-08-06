"""analytics/application -- use cases + ports."""

from __future__ import annotations

from analytics.application.audit_use_cases import AuditUseCases
from analytics.application.exceptions import AnalyticsApplicationError, UnknownReportError
from analytics.application.metric_use_cases import MetricUseCases
from analytics.application.ports import (
    AuditEntryRepository,
    ListingStatisticsProjectionRepository,
    ListingStatisticsSnapshot,
    MetricEventRepository,
)
from analytics.application.report_use_cases import ReportUseCases

__all__ = [
    "AnalyticsApplicationError",
    "AuditEntryRepository",
    "AuditUseCases",
    "ListingStatisticsProjectionRepository",
    "ListingStatisticsSnapshot",
    "MetricEventRepository",
    "MetricUseCases",
    "ReportUseCases",
    "UnknownReportError",
]
