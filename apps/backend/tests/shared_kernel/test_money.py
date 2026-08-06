"""Money -- equality/hashing, validation, arithmetic, currency handling."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from shared_kernel import CurrencyMismatchError, Money


def test_defaults_to_uzs() -> None:
    assert Money(amount=Decimal("1.00")).currency == "UZS"


def test_equal_amount_and_currency_are_equal_and_hash_equal() -> None:
    a = Money(amount=Decimal("10.00"), currency="UZS")
    b = Money(amount=Decimal("10.00"), currency="UZS")
    assert a == b
    assert hash(a) == hash(b)


def test_different_currency_same_amount_are_not_equal() -> None:
    a = Money(amount=Decimal("10.00"), currency="UZS")
    b = Money(amount=Decimal("10.00"), currency="USD")
    assert a != b


def test_I06_negative_amount_rejected() -> None:
    """# enforces: Money rejecting a negative amount is validation intrinsic to the VO."""
    with pytest.raises(ValidationError):
        Money(amount=Decimal("-0.01"), currency="UZS")


def test_more_than_two_decimal_places_rejected() -> None:
    """# enforces OpenAPI `Money.amount` "Decimal string, 2 dp"."""
    with pytest.raises(ValidationError):
        Money(amount=Decimal("1.005"), currency="UZS")


def test_zero_and_whole_amounts_are_valid() -> None:
    assert Money(amount=Decimal("0")).amount == 0
    assert Money(amount=Decimal("100")).amount == 100


def test_currency_must_be_three_chars() -> None:
    with pytest.raises(ValidationError):
        Money(amount=Decimal("1.00"), currency="US")


def test_is_immutable() -> None:
    money = Money(amount=Decimal("1.00"), currency="UZS")
    with pytest.raises(ValidationError):
        money.amount = Decimal("2.00")  # type: ignore[misc]


def test_add_same_currency() -> None:
    total = Money(amount=Decimal("10.00"), currency="UZS") + Money(
        amount=Decimal("5.50"), currency="UZS"
    )
    assert total == Money(amount=Decimal("15.50"), currency="UZS")


def test_subtract_same_currency() -> None:
    diff = Money(amount=Decimal("10.00"), currency="UZS") - Money(
        amount=Decimal("5.50"), currency="UZS"
    )
    assert diff == Money(amount=Decimal("4.50"), currency="UZS")


def test_add_different_currency_raises_currency_mismatch() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money(amount=Decimal("1.00"), currency="UZS") + Money(
            amount=Decimal("1.00"), currency="USD"
        )


def test_subtract_different_currency_raises_currency_mismatch() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money(amount=Decimal("1.00"), currency="UZS") - Money(
            amount=Decimal("1.00"), currency="USD"
        )


def test_ordering_same_currency() -> None:
    small = Money(amount=Decimal("1.00"), currency="UZS")
    big = Money(amount=Decimal("2.00"), currency="UZS")
    assert small < big
    assert not big < small


def test_ordering_different_currency_raises() -> None:
    with pytest.raises(CurrencyMismatchError):
        _ = Money(amount=Decimal("1.00"), currency="UZS") < Money(
            amount=Decimal("1.00"), currency="USD"
        )
