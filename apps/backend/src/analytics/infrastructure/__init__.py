"""analytics/infrastructure -- persistence adapters, idempotent event consumers, the
partition-precreate worker. Never imported by `interfaces/`, `application/`, or `domain/`
(DIP)."""

from __future__ import annotations

from analytics.infrastructure.event_projection import (
    handle_ads_event,
    handle_billing_event,
    handle_catalog_event,
    handle_configuration_event,
    handle_identity_event,
    handle_messaging_event,
    handle_moderation_event,
    handle_profiles_event,
)
from analytics.infrastructure.partition_worker import PartitionPrecreateWorker
from analytics.infrastructure.persistence import (
    SqlalchemyAuditEntryRepository,
    SqlalchemyListingStatisticsProjectionRepository,
    SqlalchemyMetricEventRepository,
)

__all__ = [
    "PartitionPrecreateWorker",
    "SqlalchemyAuditEntryRepository",
    "SqlalchemyListingStatisticsProjectionRepository",
    "SqlalchemyMetricEventRepository",
    "handle_ads_event",
    "handle_billing_event",
    "handle_catalog_event",
    "handle_configuration_event",
    "handle_identity_event",
    "handle_messaging_event",
    "handle_moderation_event",
    "handle_profiles_event",
]
