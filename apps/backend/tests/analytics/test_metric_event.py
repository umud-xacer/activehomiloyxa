"""Unit tests for `MetricEvent` (DDD Sec 5.13, DEC-06/BRULE-20/I-23)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from analytics.domain import (
    ImmutableFactMutationError,
    MetricEvent,
    MetricKey,
    UnknownMetricKeyError,
)
from shared_kernel import ListingId, UserId

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _make_metric(**overrides: object) -> MetricEvent:
    defaults: dict[str, object] = {
        "metric_key": "LISTING_VIEWED",
        "listing_id": ListingId(value=uuid4()),
        "user_id": UserId(value=uuid4()),
        "campaign_id": None,
        "payload": {},
        "source_event_id": uuid4(),
        "occurred_at": _NOW,
    }
    defaults.update(overrides)
    return MetricEvent.create(**defaults)  # type: ignore[arg-type]


def test_create_runs_the_closed_vocabulary_policy() -> None:
    metric = _make_metric(metric_key="FAVORITE_ADDED")
    assert metric.metric_key is MetricKey.FAVORITE_ADDED


def test_create_rejects_a_metric_key_outside_the_closed_vocabulary() -> None:
    """`MetricEvent.create` is the ONLY constructor and always validates first -- there is no
    path that stores an unknown metric key."""
    with pytest.raises(UnknownMetricKeyError):
        _make_metric(metric_key="NOT_A_REAL_METRIC")


def test_create_accepts_a_null_listing_id_for_non_listing_metrics() -> None:
    metric = _make_metric(
        metric_key="BANNER_IMPRESSION_RECORDED", listing_id=None, user_id=None, campaign_id=uuid4()
    )
    assert metric.listing_id is None
    assert metric.campaign_id is not None


# I-23: a MetricEvent is an immutable fact -- attempted mutation is rejected at the domain level.
def test_I23_attribute_assignment_is_rejected() -> None:
    metric = _make_metric()
    with pytest.raises(ImmutableFactMutationError):
        metric.metric_key = MetricKey.FAVORITE_ADDED


def test_I23_attribute_deletion_is_rejected() -> None:
    metric = _make_metric()
    with pytest.raises(ImmutableFactMutationError):
        del metric.metric_key
