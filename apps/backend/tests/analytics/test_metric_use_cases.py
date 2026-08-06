"""Unit tests for `MetricUseCases` (FR-ANALYTICS-001/002, I-23), including the projection-rebuild
capability (DB Architecture Sec 3.12: "read models... may be discarded and reprojected")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from analytics.application.metric_use_cases import MetricUseCases
from analytics.domain import UnknownMetricKeyError
from shared_kernel import ListingId, UserId

from .conftest import FakeListingStatisticsProjectionRepository, FakeMetricEventRepository

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _use_cases(
    metrics: FakeMetricEventRepository,
    listing_statistics: FakeListingStatisticsProjectionRepository,
) -> MetricUseCases:
    return MetricUseCases(metrics=metrics, listing_statistics=listing_statistics)


@pytest.mark.asyncio
async def test_record_metric_appends_the_fact(
    fake_metric_events: FakeMetricEventRepository,
    fake_listing_statistics: FakeListingStatisticsProjectionRepository,
) -> None:
    use_cases = _use_cases(fake_metric_events, fake_listing_statistics)
    metric = await use_cases.record_metric(
        metric_key="LISTING_VIEWED",
        listing_id=ListingId(value=uuid4()),
        user_id=None,
        campaign_id=None,
        payload={},
        source_event_id=uuid4(),
        occurred_at=_NOW,
    )
    assert fake_metric_events.events == [metric]


@pytest.mark.asyncio
async def test_record_metric_rejects_an_unknown_key(
    fake_metric_events: FakeMetricEventRepository,
    fake_listing_statistics: FakeListingStatisticsProjectionRepository,
) -> None:
    use_cases = _use_cases(fake_metric_events, fake_listing_statistics)
    with pytest.raises(UnknownMetricKeyError):
        await use_cases.record_metric(
            metric_key="NOT_REAL",
            listing_id=None,
            user_id=None,
            campaign_id=None,
            payload={},
            source_event_id=uuid4(),
            occurred_at=_NOW,
        )
    assert fake_metric_events.events == []


@pytest.mark.asyncio
async def test_record_metric_advances_the_listing_statistics_projection(
    fake_metric_events: FakeMetricEventRepository,
    fake_listing_statistics: FakeListingStatisticsProjectionRepository,
) -> None:
    use_cases = _use_cases(fake_metric_events, fake_listing_statistics)
    listing_id = ListingId(value=uuid4())
    await use_cases.record_metric(
        metric_key="LISTING_VIEWED",
        listing_id=listing_id,
        user_id=None,
        campaign_id=None,
        payload={},
        source_event_id=uuid4(),
        occurred_at=_NOW,
    )
    await use_cases.record_metric(
        metric_key="FAVORITE_ADDED",
        listing_id=listing_id,
        user_id=None,
        campaign_id=None,
        payload={},
        source_event_id=uuid4(),
        occurred_at=_NOW + timedelta(seconds=1),
    )
    snapshot = await use_cases.get_listing_statistics(listing_id)
    assert snapshot is not None
    assert snapshot.views == 1
    assert snapshot.favorites == 1
    assert snapshot.contact_clicks == 0


@pytest.mark.asyncio
async def test_record_metric_for_a_non_listing_family_does_not_touch_the_projection(
    fake_metric_events: FakeMetricEventRepository,
    fake_listing_statistics: FakeListingStatisticsProjectionRepository,
) -> None:
    """`BANNER_IMPRESSION_RECORDED` has no `listing_id` -- the projection stays untouched."""
    use_cases = _use_cases(fake_metric_events, fake_listing_statistics)
    await use_cases.record_metric(
        metric_key="BANNER_IMPRESSION_RECORDED",
        listing_id=None,
        user_id=None,
        campaign_id=uuid4(),
        payload={},
        source_event_id=uuid4(),
        occurred_at=_NOW,
    )
    assert fake_listing_statistics.rows == {}


@pytest.mark.asyncio
async def test_get_listing_statistics_returns_none_for_an_unknown_listing(
    fake_metric_events: FakeMetricEventRepository,
    fake_listing_statistics: FakeListingStatisticsProjectionRepository,
) -> None:
    use_cases = _use_cases(fake_metric_events, fake_listing_statistics)
    assert await use_cases.get_listing_statistics(ListingId(value=uuid4())) is None


@pytest.mark.asyncio
async def test_rebuild_listing_statistics_reconstructs_the_projection_identically(
    fake_metric_events: FakeMetricEventRepository,
    fake_listing_statistics: FakeListingStatisticsProjectionRepository,
) -> None:
    """Discard the projection, replay the MetricEvent stream, and assert the projection is
    reconstructed identically (projections are rebuildable derived data)."""
    use_cases = _use_cases(fake_metric_events, fake_listing_statistics)
    listing_a = ListingId(value=uuid4())
    listing_b = ListingId(value=uuid4())
    user = UserId(value=uuid4())

    for i, (listing, key) in enumerate(
        [
            (listing_a, "LISTING_VIEWED"),
            (listing_a, "LISTING_VIEWED"),
            (listing_a, "FAVORITE_ADDED"),
            (listing_b, "CONTACT_BUTTON_CLICKED"),
            (listing_b, "CHAT_INITIATED"),
        ]
    ):
        await use_cases.record_metric(
            metric_key=key,
            listing_id=listing,
            user_id=user,
            campaign_id=None,
            payload={},
            source_event_id=uuid4(),
            occurred_at=_NOW + timedelta(seconds=i),
        )

    before_a = await use_cases.get_listing_statistics(listing_a)
    before_b = await use_cases.get_listing_statistics(listing_b)
    assert before_a is not None
    assert before_b is not None

    replayed = await use_cases.rebuild_listing_statistics()

    assert replayed == 5
    after_a = await use_cases.get_listing_statistics(listing_a)
    after_b = await use_cases.get_listing_statistics(listing_b)
    assert after_a is not None
    assert after_b is not None
    assert (after_a.views, after_a.favorites) == (before_a.views, before_a.favorites)
    assert (after_b.contact_clicks, after_b.chats_initiated) == (
        before_b.contact_clicks,
        before_b.chats_initiated,
    )


@pytest.mark.asyncio
async def test_rebuild_listing_statistics_on_an_empty_stream_leaves_no_rows(
    fake_metric_events: FakeMetricEventRepository,
    fake_listing_statistics: FakeListingStatisticsProjectionRepository,
) -> None:
    use_cases = _use_cases(fake_metric_events, fake_listing_statistics)
    replayed = await use_cases.rebuild_listing_statistics()
    assert replayed == 0
    assert fake_listing_statistics.rows == {}
