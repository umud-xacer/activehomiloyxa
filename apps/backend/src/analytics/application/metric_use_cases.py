"""analytics/application -- `MetricUseCases` (FR-ANALYTICS-001/002, I-23). `record_metric` is
called from inside an idempotent event consumer; it appends the immutable `MetricEvent` fact and,
in the SAME call (analytics has no `outbox_event` table of its own -- Physical DB Sec 2.13's
per-module outbox list excludes `analytics`, so `MetricEventCaptured`/`AuditEntryRecorded`
(`contracts/events/analytics.py`) are in-process ingestion signals, not outbox-dispatched events),
synchronously advances the `ListingStatistics` projection. `rebuild_listing_statistics` is the
"discard the projection, replay the MetricEvent stream" capability (DB Architecture Sec 3.12:
projections "may be discarded and reprojected").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from analytics.application.ports import (
    ListingStatisticsProjectionRepository,
    ListingStatisticsSnapshot,
    MetricEventRepository,
)
from analytics.domain import MetricEvent
from shared_kernel import ListingId, UserId


class MetricUseCases:
    def __init__(
        self,
        *,
        metrics: MetricEventRepository,
        listing_statistics: ListingStatisticsProjectionRepository,
    ) -> None:
        self._metrics = metrics
        self._listing_statistics = listing_statistics

    async def record_metric(
        self,
        *,
        metric_key: str,
        listing_id: ListingId | None,
        user_id: UserId | None,
        campaign_id: UUID | None,
        payload: dict[str, Any],
        source_event_id: UUID,
        occurred_at: datetime,
    ) -> MetricEvent:
        """# enforces I-23: "only the closed v1 metric vocabulary is captured; each metric
        records exactly once per triggering event." `MetricEvent.create` runs
        `ClosedVocabularyPolicy` internally -- `UnknownMetricKeyError` propagates uncaught, never
        silently swallowed or bucketed."""
        metric = MetricEvent.create(
            metric_key=metric_key,
            listing_id=listing_id,
            user_id=user_id,
            campaign_id=campaign_id,
            payload=payload,
            source_event_id=source_event_id,
            occurred_at=occurred_at,
        )
        await self._metrics.add(metric)
        checkpoint = await self._listing_statistics.checkpoint_position()
        await self._listing_statistics.apply_metric(metric, position=checkpoint + 1)
        await self._listing_statistics.advance_checkpoint(checkpoint + 1)
        return metric

    async def get_listing_statistics(
        self, listing_id: ListingId
    ) -> ListingStatisticsSnapshot | None:
        """FR-ANALYTICS-002: "the system SHALL present basic performance statistics to listing
        owners." Ownership enforcement is the caller's job (the router checks the acting user
        against the listing before ever reaching this use case -- mirrors `catalog`'s own
        `getListingStatistics` pattern)."""
        return await self._listing_statistics.get_by_listing_id(listing_id)

    async def rebuild_listing_statistics(self) -> int:
        """Discards the projection and replays the full `MetricEvent` fact stream from position
        zero -- proves the projection is genuinely derived data, not a second source of truth.
        Returns the number of metric facts replayed."""
        await self._listing_statistics.reset()
        replayed = 0
        for metric in await self._metrics.list_all_ordered():
            replayed += 1
            await self._listing_statistics.apply_metric(metric, position=replayed)
        await self._listing_statistics.advance_checkpoint(replayed)
        return replayed
