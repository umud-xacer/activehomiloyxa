"""analytics/infrastructure/persistence -- SQLAlchemy models + repository adapters."""

from __future__ import annotations

from analytics.infrastructure.persistence.base import AnalyticsBase
from analytics.infrastructure.persistence.models import (
    AuditEntryRow,
    ListingStatisticsRow,
    MetricEventRow,
    ProcessedEventRow,
    ProjectionCheckpointRow,
)
from analytics.infrastructure.persistence.repository import (
    SqlalchemyAuditEntryRepository,
    SqlalchemyListingStatisticsProjectionRepository,
    SqlalchemyMetricEventRepository,
)

__all__ = [
    "AnalyticsBase",
    "AuditEntryRow",
    "ListingStatisticsRow",
    "MetricEventRow",
    "ProcessedEventRow",
    "ProjectionCheckpointRow",
    "SqlalchemyAuditEntryRepository",
    "SqlalchemyListingStatisticsProjectionRepository",
    "SqlalchemyMetricEventRepository",
]
