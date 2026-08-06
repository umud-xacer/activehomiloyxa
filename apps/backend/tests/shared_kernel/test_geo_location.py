"""GeoLocation -- WGS-84 bounds validation, equality/hashing, immutability."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared_kernel import GeoLocation


def test_valid_coordinate() -> None:
    point = GeoLocation(latitude=41.311151, longitude=69.279737)
    assert point.latitude == 41.311151


@pytest.mark.parametrize("latitude", [-90, 90, 0])
def test_latitude_boundary_values_are_valid(latitude: float) -> None:
    GeoLocation(latitude=latitude, longitude=0)


@pytest.mark.parametrize("latitude", [90.0001, -90.0001])
def test_latitude_out_of_range_rejected(latitude: float) -> None:
    with pytest.raises(ValidationError):
        GeoLocation(latitude=latitude, longitude=0)


@pytest.mark.parametrize("longitude", [-180, 180, 0])
def test_longitude_boundary_values_are_valid(longitude: float) -> None:
    GeoLocation(latitude=0, longitude=longitude)


@pytest.mark.parametrize("longitude", [180.0001, -180.0001])
def test_longitude_out_of_range_rejected(longitude: float) -> None:
    with pytest.raises(ValidationError):
        GeoLocation(latitude=0, longitude=longitude)


def test_equal_coordinates_are_equal_and_hash_equal() -> None:
    a = GeoLocation(latitude=1, longitude=2)
    b = GeoLocation(latitude=1, longitude=2)
    assert a == b
    assert hash(a) == hash(b)


def test_is_immutable() -> None:
    point = GeoLocation(latitude=1, longitude=2)
    with pytest.raises(ValidationError):
        point.latitude = 5  # type: ignore[misc]
