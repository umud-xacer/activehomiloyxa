"""UUIDv7 generation (Physical DB PD-01)."""

from __future__ import annotations

import time

from backbone.persistence import uuid7


def test_version_nibble_is_7() -> None:
    assert uuid7().version == 7


def test_variant_bits_are_10() -> None:
    u = uuid7()
    assert (u.int >> 62) & 0b11 == 0b10


def test_millisecond_time_ordering() -> None:
    a = uuid7()
    time.sleep(0.005)
    b = uuid7()
    time.sleep(0.005)
    c = uuid7()
    assert a < b < c


def test_generates_distinct_values() -> None:
    values = {uuid7() for _ in range(1000)}
    assert len(values) == 1000
