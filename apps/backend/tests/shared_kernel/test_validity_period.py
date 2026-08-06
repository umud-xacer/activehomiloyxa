"""ValidityPeriod -- boundary conditions (Physical DB `CHECK (valid_until > valid_from)`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from shared_kernel import ValidityPeriod

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_open_ended_period_is_valid() -> None:
    period = ValidityPeriod(valid_from=NOW)
    assert period.is_open_ended()
    assert period.valid_until is None


def test_until_strictly_after_from_is_valid() -> None:
    period = ValidityPeriod(valid_from=NOW, valid_until=NOW + timedelta(days=1))
    assert not period.is_open_ended()


def test_I07_until_equal_to_from_is_rejected() -> None:
    """# enforces Physical DB `CHECK (valid_until > valid_from)` -- strict, not >=."""
    with pytest.raises(ValidationError):
        ValidityPeriod(valid_from=NOW, valid_until=NOW)


def test_I07_until_before_from_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ValidityPeriod(valid_from=NOW, valid_until=NOW - timedelta(seconds=1))


def test_contains_within_period() -> None:
    period = ValidityPeriod(valid_from=NOW, valid_until=NOW + timedelta(days=10))
    assert period.contains(NOW + timedelta(days=5))


def test_contains_excludes_until_boundary() -> None:
    period = ValidityPeriod(valid_from=NOW, valid_until=NOW + timedelta(days=10))
    assert not period.contains(NOW + timedelta(days=10))


def test_contains_includes_from_boundary() -> None:
    period = ValidityPeriod(valid_from=NOW, valid_until=NOW + timedelta(days=10))
    assert period.contains(NOW)


def test_contains_before_from_is_false() -> None:
    period = ValidityPeriod(valid_from=NOW, valid_until=NOW + timedelta(days=10))
    assert not period.contains(NOW - timedelta(seconds=1))


def test_open_ended_contains_far_future() -> None:
    period = ValidityPeriod(valid_from=NOW)
    assert period.contains(NOW + timedelta(days=36500))


def test_equal_periods_are_equal_and_hash_equal() -> None:
    a = ValidityPeriod(valid_from=NOW, valid_until=NOW + timedelta(days=1))
    b = ValidityPeriod(valid_from=NOW, valid_until=NOW + timedelta(days=1))
    assert a == b
    assert hash(a) == hash(b)


def test_is_immutable() -> None:
    period = ValidityPeriod(valid_from=NOW)
    with pytest.raises(ValidationError):
        period.valid_from = NOW  # type: ignore[misc]
