"""Money -- shared kernel value object (DDD Sec 5.14; OpenAPI `Money`)."""

from __future__ import annotations

from decimal import Decimal
from functools import total_ordering

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CurrencyMismatchError(ValueError):
    """Raised when an arithmetic/comparison operation is attempted between two `Money` values
    of different currencies -- adding UZS to USD has no defined result."""

    def __init__(self, left: str, right: str) -> None:
        self.left = left
        self.right = right
        super().__init__(f"cannot combine Money in different currencies: {left} vs {right}")


@total_ordering
class Money(BaseModel):
    """A decimal amount with a currency code. `amount` is a non-negative, 2-dp decimal (never a
    float -- OpenAPI `Money.amount` is a decimal string for the same reason). Rejecting a
    negative amount or a value with more than 2 decimal places is validation intrinsic to the
    value object itself, not a business rule about what the money is used for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    amount: Decimal
    currency: str = Field(min_length=3, max_length=3, default="UZS")

    @model_validator(mode="after")
    def _validate_amount(self) -> Money:
        if self.amount < 0:
            raise ValueError(f"Money.amount must not be negative, got {self.amount}")
        exponent = self.amount.normalize().as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError(f"Money.amount must have at most 2 decimal places, got {self.amount}")
        return self

    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)

    def __add__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __lt__(self, other: Money) -> bool:
        self._require_same_currency(other)
        return self.amount < other.amount
