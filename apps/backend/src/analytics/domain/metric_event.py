"""analytics/domain -- `MetricEvent` [P], the immutable engagement fact from the closed v1
metric vocabulary (DDD Sec 5.13, DEC-06/BRULE-20/I-23). Append-only, same immutability
discipline as `AuditEntry`. `MetricEvent.create` is the ONLY constructor and always runs
`ClosedVocabularyPolicy.validate` first -- there is no path that stores a metric key outside the
closed set.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from analytics.domain.exceptions import ImmutableFactMutationError
from analytics.domain.value_objects import ClosedVocabularyPolicy, MetricKey
from shared_kernel import ListingId, UserId


@dataclass
class MetricEvent:
    """Vocabulary key, subject refs (identifier-only, never dereferenced -- Database
    Architecture Sec 3.12), timestamp, dedup key (I-23: exactly once per triggering event)."""

    id: UUID
    occurred_at: datetime
    metric_key: MetricKey
    listing_id: ListingId | None
    user_id: UserId | None
    campaign_id: UUID | None
    payload: dict[str, Any]
    source_event_id: UUID
    """Dedup key -- the triggering `EventEnvelope.event_id` (I-23: "each metric records exactly
    once per triggering event"). Persisted in `UNIQUE (source_event_id, occurred_at)`."""

    def __setattr__(self, name: str, value: object) -> None:
        raise ImmutableFactMutationError("MetricEvent")

    def __delattr__(self, name: str) -> None:
        raise ImmutableFactMutationError("MetricEvent")

    @staticmethod
    def create(
        *,
        metric_key: str,
        listing_id: ListingId | None,
        user_id: UserId | None,
        campaign_id: UUID | None,
        payload: dict[str, Any],
        source_event_id: UUID,
        occurred_at: datetime,
        event_id: UUID | None = None,
    ) -> MetricEvent:
        validated_key = ClosedVocabularyPolicy.validate(metric_key)
        instance = MetricEvent.__new__(MetricEvent)
        object.__setattr__(instance, "id", event_id or uuid4())
        object.__setattr__(instance, "occurred_at", occurred_at)
        object.__setattr__(instance, "metric_key", validated_key)
        object.__setattr__(instance, "listing_id", listing_id)
        object.__setattr__(instance, "user_id", user_id)
        object.__setattr__(instance, "campaign_id", campaign_id)
        object.__setattr__(instance, "payload", payload)
        object.__setattr__(instance, "source_event_id", source_event_id)
        return instance
