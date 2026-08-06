"""`billing.domain.invoice.Invoice` -- the guarded lifecycle (`Issued -> Paid | Void`, both
terminal)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from billing.domain import IllegalInvoiceStateTransitionError, Invoice
from shared_kernel import Money

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _invoice(**overrides: object) -> Invoice:
    defaults: dict[str, object] = {
        "invoice_id": uuid4(),
        "order_id": uuid4(),
        "invoice_number": "INV-000001",
        "amount": Money(amount=Decimal("50000.00"), currency="UZS"),
        "now": _NOW,
    }
    defaults.update(overrides)
    return Invoice.issue(**defaults)  # type: ignore[arg-type]


class TestInvoiceIssue:
    def test_I01_issued_with_no_payment_confirmation(self) -> None:
        invoice = _invoice()
        assert invoice.status.value == "ISSUED"
        assert invoice.payment_confirmation is None


class TestConfirmPayment:
    def test_I02_confirm_payment_moves_issued_to_paid(self) -> None:
        operator_id = uuid4()
        confirmed = _invoice().confirm_payment(confirmed_by=operator_id, note="ok", now=_NOW)
        assert confirmed.status.value == "PAID"
        assert confirmed.payment_confirmation is not None
        assert confirmed.payment_confirmation.confirmed_by == operator_id
        assert confirmed.payment_confirmation.confirmed_at == _NOW
        assert confirmed.payment_confirmation.note == "ok"

    def test_I03_confirm_payment_twice_raises(self) -> None:
        invoice = _invoice().confirm_payment(confirmed_by=uuid4(), note=None, now=_NOW)
        with pytest.raises(IllegalInvoiceStateTransitionError):
            invoice.confirm_payment(confirmed_by=uuid4(), note=None, now=_NOW)

    def test_I04_confirm_payment_after_void_raises(self) -> None:
        invoice = _invoice().void(now=_NOW)
        with pytest.raises(IllegalInvoiceStateTransitionError):
            invoice.confirm_payment(confirmed_by=uuid4(), note=None, now=_NOW)


class TestVoid:
    def test_I05_void_moves_issued_to_void(self) -> None:
        voided = _invoice().void(now=_NOW)
        assert voided.status.value == "VOID"

    def test_I06_void_after_paid_raises(self) -> None:
        invoice = _invoice().confirm_payment(confirmed_by=uuid4(), note=None, now=_NOW)
        with pytest.raises(IllegalInvoiceStateTransitionError):
            invoice.void(now=_NOW)

    def test_I07_void_twice_raises(self) -> None:
        invoice = _invoice().void(now=_NOW)
        with pytest.raises(IllegalInvoiceStateTransitionError):
            invoice.void(now=_NOW)
