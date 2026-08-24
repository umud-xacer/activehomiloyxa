"""billing/infrastructure/payment_gateway/mock.py -- listing paywall (2026-08-23). Mock payment
provider: a `PaymentProviderPort` implementation with no real gateway behind it at all, standing
in for Payme/Click/Uzum until real merchant credentials exist (FR-BILL-004/BRULE-15: "online
providers can be added in v2 without changing business logic" -- this is the proof that swap-in
works, exercised before any real merchant account exists rather than after).

Mirrors `click.py`'s own `ClickAdapter`/`ClickMerchantApi` split exactly, minus the parts that
only exist because Click is a real external system (MD5 signature verification, a two-step
Prepare/Complete handshake, form-encoded wire parsing): `MockMerchantApi.pay` is a single call
that creates-and-immediately-marks-`PERFORMED` one `ProviderTransaction` row (provider="MOCK"),
then confirms payment through `PaymentUseCases.confirm_payment` the same way Click's own
`complete()` does. `MockAdapter.confirm()` still verifies a real `PERFORMED` row rather than
trusting `confirmed=True` blindly -- even the mock path can't activate an entitlement without
going through `pay()` first, the same discipline `ClickAdapter`/`PaymeAdapter` already apply.

Whether `POST /payments/mock/pay` is reachable at all is gated by `main.py` on the `.env`
`PAYMENT_PROVIDER` variable (`mock|payme|click`, default `offline`) -- unlike Payme/Click's routes
(always mounted, each protected by its own signature verification), this endpoint has no
verification of its own and is a free instant-pay backdoor by design, so it must not exist in the
ASGI app at all unless explicitly turned on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from billing.application.exceptions import InvoiceNotFoundError, OrderNotFoundError
from billing.application.payment_use_cases import PaymentUseCases
from billing.application.ports import InvoiceRepository
from billing.domain.exceptions import BillingDomainError
from billing.domain.value_objects import InvoiceStatus
from billing.infrastructure.payment_gateway.provider_transactions import (
    ProviderTransactionRepository,
)

SYSTEM_OPERATOR_ID = UUID("00000000-0000-0000-0000-0000000000f3")
"""Fixed non-human system principal for mock-confirmed payments -- sibling of
`click.SYSTEM_OPERATOR_ID` (`...f2`) / `payme.SYSTEM_OPERATOR_ID` (`...f1`)."""


class MockPaymentError(Exception):
    """Carries a human-readable reason straight to the webhook envelope
    (`webhook_routers.mock_pay`)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class MockAdapter:
    """Implements `billing.application.ports.PaymentProviderPort` -- same shape and rationale as
    `ClickAdapter`/`PaymeAdapter`, registered only via `composition_root.provide_mock_merchant_api`."""

    def __init__(self, transactions: ProviderTransactionRepository) -> None:
        self._transactions = transactions

    async def confirm(
        self,
        *,
        invoice_id: UUID,
        confirmed: bool,
        operator_account_id: UUID,
        note: str | None,
    ) -> bool:
        if not confirmed:
            return False
        transaction = await self._transactions.get_by_invoice(invoice_id, provider="MOCK")
        return transaction is not None and transaction.state == "PERFORMED"


@dataclass(frozen=True)
class MockPayRequest:
    invoice_id: UUID
    provider_label: str
    """Display-only (e.g. `"UZUM"`, `"PAYME"`, `"CLICK"`) -- which demo button the frontend
    clicked; not a real provider selection, doesn't affect behaviour. Recorded verbatim into the
    `Invoice.confirm_payment` note so a demo-paid invoice still shows which button was used."""


class MockMerchantApi:
    """Sibling of `PaymeMerchantApi`/`ClickMerchantApi` -- no Prepare/Complete split needed since
    there's no real gateway round-trip to model, just one call that does both steps at once."""

    def __init__(
        self,
        *,
        invoices: InvoiceRepository,
        transactions: ProviderTransactionRepository,
        payment_use_cases: PaymentUseCases,
    ) -> None:
        self._invoices = invoices
        self._transactions = transactions
        self._payment_use_cases = payment_use_cases

    async def pay(self, request: MockPayRequest) -> dict[str, object]:
        invoice = await self._invoices.get_by_id(request.invoice_id)
        if invoice is None:
            raise MockPaymentError("Invoice not found")

        existing = await self._transactions.get_by_invoice(invoice.id, provider="MOCK")
        now = datetime.now(UTC)
        if existing is None:
            if invoice.status is not InvoiceStatus.ISSUED:
                raise MockPaymentError("Invoice is not payable")
            existing = await self._transactions.create(
                transaction_id=uuid4(),
                invoice_id=invoice.id,
                provider="MOCK",
                provider_transaction_id=f"mock-{uuid4()}",
                amount=invoice.amount.amount,
                now=now,
            )

        if existing.state == "PERFORMED":
            return {"invoiceId": str(invoice.id), "status": "PAID"}

        performed = await self._transactions.mark_performed(existing.id, now=now)
        try:
            await self._payment_use_cases.confirm_payment(
                invoice_id=performed.invoice_id,
                operator_account_id=SYSTEM_OPERATOR_ID,
                confirmed=True,
                note=f"Mock payment via {request.provider_label}",
                now=now,
            )
        except (InvoiceNotFoundError, OrderNotFoundError, BillingDomainError) as exc:
            raise MockPaymentError(str(exc)) from exc
        return {"invoiceId": str(invoice.id), "status": "PAID"}
