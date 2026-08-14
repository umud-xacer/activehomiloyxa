"""billing/infrastructure/payment_gateway/click.py -- ADR-0010. Click Shop API (`Prepare`/
`Complete` handshake) v2 online-provider integration for
`billing.application.ports.PaymentProviderPort`. Mirrors `payme.py`'s own split exactly:
`ClickAdapter` is the `PaymentProviderPort.confirm()` implementation (verifies a `PERFORMED`
`ProviderTransaction` row), `ClickMerchantApi` is the protocol logic Click's server calls
synchronously, kept ASGI-request-free so it is unit-testable on its own.

Click's own wire protocol differs from Payme's in three ways this module has to account for:
amounts are sent as decimal so'm strings (not integer tiyin), the merchant reference travels as
`merchant_trans_id` rather than a JSON-RPC `account` object, and the handshake is two named
actions (`action=0` Prepare, `action=1` Complete) rather than six named JSON-RPC methods --
`webhook_routers.py` exposes them as two separate routes (`/payments/click/prepare`,
`/payments/click/complete`) rather than one dispatched-by-`action` route, matching how Click's own
merchant cabinet has historically configured Prepare URL/Complete URL as two distinct fields.

Known, deliberate v1 simplification: `Complete`'s inbound `error` field (Click's own signal that
IT cancelled the transaction, e.g. the buyer cancelled the OTP step) is mapped straight to our
`CANCELLED` state with no attempt to distinguish Click's finer-grained cancellation reasons --
sufficient for "this money was never captured," which is the only fact `PaymentUseCases` needs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from billing.application.exceptions import InvoiceNotFoundError, OrderNotFoundError
from billing.application.payment_use_cases import PaymentUseCases
from billing.application.ports import InvoiceRepository
from billing.domain import Invoice
from billing.domain.exceptions import BillingDomainError
from billing.domain.value_objects import InvoiceStatus
from billing.infrastructure.payment_gateway.provider_transactions import (
    ProviderTransactionRepository,
)

SYSTEM_OPERATOR_ID = UUID("00000000-0000-0000-0000-0000000000f2")
"""Fixed non-human system principal for gateway-confirmed payments -- Click's own sibling of
`payme.SYSTEM_OPERATOR_ID` (same rationale, a distinct UUID so a `PaymentConfirmation.
confirmed_by` value is always attributable to exactly one provider)."""

# Click's own fixed webhook error codes (Click Shop API reference).
ERR_SIGN_CHECK_FAILED = -1
ERR_INCORRECT_AMOUNT = -2
ERR_ALREADY_PAID = -4
ERR_ORDER_NOT_FOUND = -5
ERR_TRANSACTION_NOT_FOUND = -6
ERR_FAILED_TO_UPDATE = -7
ERR_TRANSACTION_CANCELLED = -9


class ClickError(Exception):
    """Carries a Click `error`/`error_note` pair straight to the webhook envelope
    (`webhook_routers.click_prepare`/`click_complete`)."""

    def __init__(self, code: int, note: str) -> None:
        self.code = code
        self.note = note
        super().__init__(note)


@dataclass(frozen=True)
class ClickPrepareRequest:
    click_trans_id: str
    service_id: str
    merchant_trans_id: str
    """Our `Invoice.id`, sent by the frontend as Click's `merchant_trans_id` checkout param --
    the `merchant_trans_id`/`invoice_id` naming mismatch is Click's own field name, not ours."""
    amount: Decimal
    amount_raw: str
    """The exact string Click sent, kept alongside the parsed `Decimal` -- signature verification
    must hash the byte-for-byte original text, not a re-serialized `Decimal`."""
    action: int
    sign_time: str
    sign_string: str


@dataclass(frozen=True)
class ClickCompleteRequest:
    click_trans_id: str
    service_id: str
    merchant_trans_id: str
    merchant_prepare_id: str
    amount: Decimal
    amount_raw: str
    action: int
    error: int
    sign_time: str
    sign_string: str


def verify_prepare_signature(request: ClickPrepareRequest, secret_key: str) -> bool:
    raw = (
        f"{request.click_trans_id}{request.service_id}{secret_key}"
        f"{request.merchant_trans_id}{request.amount_raw}{request.action}{request.sign_time}"
    )
    return hashlib.md5(raw.encode()).hexdigest() == request.sign_string.lower()


def verify_complete_signature(request: ClickCompleteRequest, secret_key: str) -> bool:
    raw = (
        f"{request.click_trans_id}{request.service_id}{secret_key}"
        f"{request.merchant_trans_id}{request.merchant_prepare_id}"
        f"{request.amount_raw}{request.action}{request.sign_time}"
    )
    return hashlib.md5(raw.encode()).hexdigest() == request.sign_string.lower()


class ClickAdapter:
    """Implements `billing.application.ports.PaymentProviderPort` -- same shape and rationale as
    `payme.PaymeAdapter`, registered only on `composition_root.provide_click_payment_use_cases`."""

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
        transaction = await self._transactions.get_by_invoice(
            invoice_id, provider="CLICK"
        )
        return transaction is not None and transaction.state == "PERFORMED"


class ClickMerchantApi:
    """`merchant_trans_id` is always our `Invoice.id` -- the Click sibling of
    `PaymeMerchantApi`'s `account.invoice_id` convention, chosen for the same reason (no extra
    `Order` lookup needed to place a `ProviderTransaction` row)."""

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

    async def prepare(self, request: ClickPrepareRequest) -> dict[str, object]:
        invoice = await self._resolve_invoice(request.merchant_trans_id)

        existing = await self._transactions.get_by_provider_transaction_id(
            provider="CLICK", provider_transaction_id=request.click_trans_id
        )
        if existing is not None:
            return {"merchant_prepare_id": str(existing.id)}

        existing_for_invoice = await self._transactions.get_by_invoice(
            invoice.id, provider="CLICK"
        )
        if existing_for_invoice is not None:
            return {"merchant_prepare_id": str(existing_for_invoice.id)}

        if invoice.status is not InvoiceStatus.ISSUED:
            raise ClickError(ERR_ALREADY_PAID, "Invoice is not payable")
        if request.amount != invoice.amount.amount:
            raise ClickError(ERR_INCORRECT_AMOUNT, "Incorrect amount")

        created = await self._transactions.create(
            transaction_id=uuid4(),
            invoice_id=invoice.id,
            provider="CLICK",
            provider_transaction_id=request.click_trans_id,
            amount=invoice.amount.amount,
            now=datetime.now(UTC),
        )
        return {"merchant_prepare_id": str(created.id)}

    async def complete(self, request: ClickCompleteRequest) -> dict[str, object]:
        transaction = await self._transactions.get_by_provider_transaction_id(
            provider="CLICK", provider_transaction_id=request.click_trans_id
        )
        if transaction is None:
            raise ClickError(ERR_TRANSACTION_NOT_FOUND, "Transaction not found")
        if str(transaction.id) != request.merchant_prepare_id:
            raise ClickError(
                ERR_TRANSACTION_NOT_FOUND, "merchant_prepare_id does not match"
            )

        if request.error < 0:
            cancelled = await self._transactions.mark_cancelled(
                transaction.id,
                reason=f"click error {request.error}",
                now=datetime.now(UTC),
            )
            return {"merchant_confirm_id": str(cancelled.id)}

        if transaction.state == "PERFORMED":
            return {"merchant_confirm_id": str(transaction.id)}
        if transaction.state == "CANCELLED":
            raise ClickError(ERR_TRANSACTION_CANCELLED, "Transaction is cancelled")

        now = datetime.now(UTC)
        performed = await self._transactions.mark_performed(transaction.id, now=now)
        try:
            await self._payment_use_cases.confirm_payment(
                invoice_id=performed.invoice_id,
                operator_account_id=SYSTEM_OPERATOR_ID,
                confirmed=True,
                note=f"Click transaction {performed.provider_transaction_id}",
                now=now,
            )
        except (InvoiceNotFoundError, OrderNotFoundError, BillingDomainError) as exc:
            raise ClickError(ERR_FAILED_TO_UPDATE, str(exc)) from exc
        return {"merchant_confirm_id": str(performed.id)}

    async def _resolve_invoice(self, merchant_trans_id: str) -> Invoice:
        try:
            invoice_id = UUID(merchant_trans_id)
        except ValueError as exc:
            raise ClickError(ERR_ORDER_NOT_FOUND, "Order not found") from exc
        invoice = await self._invoices.get_by_id(invoice_id)
        if invoice is None:
            raise ClickError(ERR_ORDER_NOT_FOUND, "Order not found")
        return invoice
