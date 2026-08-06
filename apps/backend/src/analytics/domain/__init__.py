"""analytics/domain -- aggregates, value objects, policies, typed exceptions. Depends on nothing
outside `shared_kernel` (Absolute Architecture Rule 1)."""

from __future__ import annotations

from analytics.domain.audit_entry import AuditEntry
from analytics.domain.exceptions import (
    AnalyticsDomainError,
    ImmutableFactMutationError,
    UnknownMetricKeyError,
)
from analytics.domain.metric_event import MetricEvent
from analytics.domain.value_objects import ClosedVocabularyPolicy, MetricKey

__all__ = [
    "AnalyticsDomainError",
    "AuditEntry",
    "ClosedVocabularyPolicy",
    "ImmutableFactMutationError",
    "MetricEvent",
    "MetricKey",
    "UnknownMetricKeyError",
]
