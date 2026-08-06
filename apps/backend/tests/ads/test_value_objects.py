"""Unit tests for `ads.domain.value_objects` -- `Schedule`/`Targeting` (FR-BANNER-002/003)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from ads.domain import InvalidScheduleError, Schedule, Targeting

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def test_schedule_rejects_end_before_start() -> None:
    with pytest.raises(InvalidScheduleError):
        Schedule(start=_NOW, end=_NOW - timedelta(days=1), priority=0)


def test_schedule_rejects_end_equal_to_start() -> None:
    with pytest.raises(InvalidScheduleError):
        Schedule(start=_NOW, end=_NOW, priority=0)


def test_schedule_rejects_negative_priority() -> None:
    with pytest.raises(InvalidScheduleError):
        Schedule(start=_NOW, end=_NOW + timedelta(days=1), priority=-1)


def test_schedule_covers_is_inclusive_start_exclusive_end() -> None:
    schedule = Schedule(start=_NOW, end=_NOW + timedelta(days=1), priority=0)
    assert schedule.covers(_NOW) is True
    assert schedule.covers(_NOW + timedelta(hours=12)) is True
    assert schedule.covers(_NOW + timedelta(days=1)) is False
    assert schedule.covers(_NOW - timedelta(seconds=1)) is False


def test_untargeted_targeting_matches_everything() -> None:
    targeting = Targeting()
    assert targeting.matches(category_id=None, geo=None, language=None) is True
    assert targeting.matches(category_id=uuid4(), geo="UZ-TAS", language="ru") is True


def test_category_targeting_requires_a_matching_category_id() -> None:
    category_id = uuid4()
    targeting = Targeting(category_ids=(category_id,))
    assert targeting.matches(category_id=category_id, geo=None, language=None) is True
    assert targeting.matches(category_id=uuid4(), geo=None, language=None) is False
    assert targeting.matches(category_id=None, geo=None, language=None) is False


def test_geo_targeting_requires_an_exact_match() -> None:
    targeting = Targeting(geo="UZ-TAS")
    assert targeting.matches(category_id=None, geo="UZ-TAS", language=None) is True
    assert targeting.matches(category_id=None, geo="UZ-SAM", language=None) is False
    assert targeting.matches(category_id=None, geo=None, language=None) is False


def test_language_targeting_requires_membership() -> None:
    targeting = Targeting(languages=("ru", "en"))
    assert targeting.matches(category_id=None, geo=None, language="ru") is True
    assert targeting.matches(category_id=None, geo=None, language="uz_latn") is False
    assert targeting.matches(category_id=None, geo=None, language=None) is False


def test_all_three_dimensions_must_match_simultaneously() -> None:
    category_id = uuid4()
    targeting = Targeting(category_ids=(category_id,), geo="UZ-TAS", languages=("ru",))
    assert targeting.matches(category_id=category_id, geo="UZ-TAS", language="ru") is True
    assert targeting.matches(category_id=category_id, geo="UZ-SAM", language="ru") is False
