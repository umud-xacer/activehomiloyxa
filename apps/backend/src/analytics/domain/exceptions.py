"""analytics/domain -- typed exceptions, each named for the invariant it protects."""

from __future__ import annotations


class AnalyticsDomainError(Exception):
    """Base for every analytics domain-layer error."""


class UnknownMetricKeyError(AnalyticsDomainError):
    """# enforces I-23/BRULE-20/DEC-06: `ClosedVocabularyPolicy` rejects any metric key outside
    the eight-key v1 vocabulary. Raised by `ClosedVocabularyPolicy.validate`, never silently
    swallowed or bucketed into a generic/"other" category."""

    def __init__(self, metric_key: str) -> None:
        self.metric_key = metric_key
        super().__init__(
            f"{metric_key!r} is not in the closed v1 metric vocabulary "
            "(DEC-06/BRULE-20) -- rejected, not stored"
        )


class ImmutableFactMutationError(AnalyticsDomainError):
    """# enforces I-22 (AuditEntry)/I-23 (MetricEvent): both facts are immutable once
    constructed. Raised by any attempted mutation at the domain level -- the database-level
    guard trigger (PD-07) is the second, independent layer of the same invariant."""

    def __init__(self, aggregate_name: str) -> None:
        self.aggregate_name = aggregate_name
        super().__init__(f"{aggregate_name} is an immutable fact -- it cannot be mutated")
