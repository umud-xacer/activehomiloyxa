"""billing/infrastructure/payment_gateway/payme.py -- ADR-0010. Payme Business API ("Subscribe
API") v2 online-provider integration for `billing.application.ports.PaymentProviderPort`.

Two responsibilities, kept in one file per this package's own `__init__.py` docstring ("the real
protocol complexity here ... lives entirely in payme.py/click.py"):

1. `PaymeAdapter` -- the actual `PaymentProviderPort.confirm()` implementation: verifies a
   `ProviderTransaction` row already reached `PERFORMED` for this invoice before agreeing to
   confirm. Not used by `PerformTransaction` below (which calls `PaymentUseCases.confirm_payment`
   directly, itself constructed WITH this adapter at the composition root -- see
   `composition_root.provide_payme_payment_use_cases`) -- it exists so `confirm_payment`'s own
   `self._payment_provider.confirm(...)` call has something real to check against rather than the
   offline adapter's unconditional `return confirmed`, matching the port's own docstring ("A v2
   online-provider adapter would instead verify a referenced provider transaction here").
2. `PaymeMerchantApi` -- the JSON-RPC 2.0 method dispatch Payme's own server calls synchronously
   on every checkout step (`CheckPerformTransaction`/`CreateTransaction`/`PerformTransaction`/
   `CancelTransaction`/`CheckTransaction`/`GetStatement`). Not a FastAPI route itself --
   `billing.infrastructure.payment_gateway.webhook_routers` is the thin HTTP/Basic-Auth/JSON-RPC
   envelope around this class, kept separate so the protocol logic is unit-testable without a
   live ASGI request.

Known, deliberate v1 simplifications (documented, not hidden): no `SetFiscalData` support (no
fiscal-receipt integration exists anywhere in this codebase yet), no enforcement of Payme's
merchant-cabinet-configured "create within N ms of account creation" window (this app has no
per-merchant policy store for it -- `CreateTransaction` accepts any request that otherwise
validates), no reason-code translation on `CancelTransaction` (Payme's integer reason code is
stored verbatim as text, not mapped to a human explanation). All are additive, backward-compatible
follow-ons, not corrections -- ADR-0010 itself notes "end-to-end payment testing is blocked on
real merchant accounts, sandbox/unit verification only until then"; the exact error-code choices
below are best-effort against Payme's public Business API reference and should get one live
sandbox pass once real credentials exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from billing.application.exceptions import InvoiceNotFoundError, OrderNotFoundError
from billing.application.payment_use_cases import PaymentUseCases
from billing.application.ports import InvoiceRepository
from billing.domain import Invoice
from billing.domain.exceptions import BillingDomainError
from billing.domain.value_objects import InvoiceStatus
from billing.infrastructure.payment_gateway.provider_transactions import (
    ProviderTransaction,
    ProviderTransactionRepository,
)

SYSTEM_OPERATOR_ID = UUID("00000000-0000-0000-0000-0000000000f1")
"""Fixed non-human system principal for gateway-confirmed payments -- same precedent as
`configuration.interfaces.routers._SOLO_ADMIN_CHECKER_ID`: Payme's own server, having already
walked its state machine to `PerformTransaction`, IS the attestation; there is no human operator
account to attribute `PaymentConfirmation.confirmed_by` to."""


class PaymeError(Exception):
    """Carries a Payme JSON-RPC `error.code`/`error.message` pair straight to the webhook
    envelope (`webhook_routers.payme_webhook`)."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# Payme's own fixed JSON-RPC error codes (Payme Business API reference).
ERR_INVALID_AMOUNT = -31001
ERR_ACCOUNT_NOT_FOUND = -31050
ERR_ALREADY_HAS_TRANSACTION = -31051
ERR_TRANSACTION_NOT_FOUND = -31003
ERR_UNABLE_TO_PERFORM = -31008
METHOD_NOT_FOUND = -32601


def _to_tiyin(amount: Decimal) -> int:
    """Payme amounts are integer tiyin (1/100 so'm); `Invoice.amount.amount` is a 2dp `Decimal`
    so'm value (`shared_kernel.Money`)."""
    return int((amount * 100).to_integral_exact())


def _from_ms(time_ms: int) -> datetime:
    return datetime.fromtimestamp(time_ms / 1000, tz=UTC)


def _to_ms(dt: datetime | None) -> int:
    return int(dt.timestamp() * 1000) if dt is not None else 0


def _payme_state(transaction: ProviderTransaction) -> int:
    """Payme's own `state` vocabulary: 1 = created, 2 = performed, -1 = cancelled before perform,
    -2 = cancelled after perform."""
    if transaction.state == "PERFORMED":
        return 2
    if transaction.state == "CANCELLED":
        return -2 if transaction.performed_at is not None else -1
    return 1


class PaymeAdapter:
    """Implements `billing.application.ports.PaymentProviderPort`. Registered ONLY on the
    payment-use-cases instance the Payme webhook router constructs
    (`composition_root.provide_payme_payment_use_cases`) -- never on the general
    `provide_payment_use_cases()` the admin `confirmInvoicePayment` endpoint uses, which stays on
    `OfflineManualPaymentAdapter` (BRULE-15's v1 default is unchanged by this ADR)."""

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
            invoice_id, provider="PAYME"
        )
        return transaction is not None and transaction.state == "PERFORMED"


class PaymeMerchantApi:
    """The JSON-RPC method dispatch. One instance per request, constructed by the webhook router
    with the same `AsyncSession`-bound repositories/use-cases the composition root wires for
    `provide_payme_payment_use_cases` -- mirrors `PaymentUseCases`' own "share one session"
    discipline, so `PerformTransaction`'s provider-transaction update and its `confirm_payment`
    call commit or roll back together.

    `account` is always `{"invoice_id": "<our Invoice.id>"}` -- Payme's merchant cabinet lets the
    integrator choose the account field name/shape; `invoice_id` is used directly (rather than
    routing through `Order`) because `ProviderTransactionRow.invoice_id` is the row's own FK
    target, so no extra Order lookup is needed to place a transaction."""

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

    async def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        handler = {
            "CheckPerformTransaction": self._check_perform_transaction,
            "CreateTransaction": self._create_transaction,
            "PerformTransaction": self._perform_transaction,
            "CancelTransaction": self._cancel_transaction,
            "CheckTransaction": self._check_transaction,
            "GetStatement": self._get_statement,
        }.get(method)
        if handler is None:
            raise PaymeError(METHOD_NOT_FOUND, "Method not found")
        return await handler(params)

    async def _resolve_invoice(self, account: dict[str, Any]) -> Invoice:
        raw_id = account.get("invoice_id")
        if not raw_id:
            raise PaymeError(ERR_ACCOUNT_NOT_FOUND, "invoice_id is required")
        try:
            invoice_id = UUID(str(raw_id))
        except ValueError as exc:
            raise PaymeError(
                ERR_ACCOUNT_NOT_FOUND, "invoice_id is not a valid identifier"
            ) from exc
        invoice = await self._invoices.get_by_id(invoice_id)
        if invoice is None:
            raise PaymeError(ERR_ACCOUNT_NOT_FOUND, "Order not found")
        return invoice

    async def _check_perform_transaction(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        invoice = await self._resolve_invoice(params.get("account") or {})
        if invoice.status is not InvoiceStatus.ISSUED:
            raise PaymeError(ERR_UNABLE_TO_PERFORM, "Invoice is not payable")
        if int(params.get("amount", -1)) != _to_tiyin(invoice.amount.amount):
            raise PaymeError(ERR_INVALID_AMOUNT, "Incorrect amount")
        return {"allow": True}

    async def _create_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        provider_transaction_id = str(params["id"])
        invoice = await self._resolve_invoice(params.get("account") or {})
        if int(params.get("amount", -1)) != _to_tiyin(invoice.amount.amount):
            raise PaymeError(ERR_INVALID_AMOUNT, "Incorrect amount")

        existing_by_provider_id = (
            await self._transactions.get_by_provider_transaction_id(
                provider="PAYME", provider_transaction_id=provider_transaction_id
            )
        )
        if existing_by_provider_id is not None:
            return _create_transaction_response(existing_by_provider_id)

        existing_for_invoice = await self._transactions.get_by_invoice(
            invoice.id, provider="PAYME"
        )
        if existing_for_invoice is not None:
            raise PaymeError(
                ERR_ALREADY_HAS_TRANSACTION, "Order already has a transaction"
            )

        if invoice.status is not InvoiceStatus.ISSUED:
            raise PaymeError(ERR_UNABLE_TO_PERFORM, "Invoice is not payable")

        created = await self._transactions.create(
            transaction_id=uuid4(),
            invoice_id=invoice.id,
            provider="PAYME",
            provider_transaction_id=provider_transaction_id,
            amount=invoice.amount.amount,
            now=datetime.now(UTC),
        )
        return _create_transaction_response(created)

    async def _perform_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        transaction = await self._get_transaction_or_raise(str(params["id"]))
        if transaction.state == "PERFORMED":
            return _perform_transaction_response(transaction)
        if transaction.state == "CANCELLED":
            raise PaymeError(ERR_UNABLE_TO_PERFORM, "Transaction is cancelled")

        now = datetime.now(UTC)
        performed = await self._transactions.mark_performed(transaction.id, now=now)
        try:
            await self._payment_use_cases.confirm_payment(
                invoice_id=performed.invoice_id,
                operator_account_id=SYSTEM_OPERATOR_ID,
                confirmed=True,
                note=f"Payme transaction {performed.provider_transaction_id}",
                now=now,
            )
        except (InvoiceNotFoundError, OrderNotFoundError, BillingDomainError) as exc:
            raise PaymeError(ERR_UNABLE_TO_PERFORM, str(exc)) from exc
        return _perform_transaction_response(performed)

    async def _cancel_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        transaction = await self._get_transaction_or_raise(str(params["id"]))
        if transaction.state == "CANCELLED":
            return _cancel_transaction_response(transaction)
        reason = str(params.get("reason", ""))
        cancelled = await self._transactions.mark_cancelled(
            transaction.id, reason=reason, now=datetime.now(UTC)
        )
        return _cancel_transaction_response(cancelled)

    async def _check_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        transaction = await self._get_transaction_or_raise(str(params["id"]))
        return _check_transaction_response(transaction)

    async def _get_statement(self, params: dict[str, Any]) -> dict[str, Any]:
        start = _from_ms(int(params["from"]))
        end = _from_ms(int(params["to"]))
        transactions = await self._transactions.list_between(
            provider="PAYME", start=start, end=end
        )
        return {
            "transactions": [
                {**_check_transaction_response(t), "amount": _to_tiyin(t.amount)}
                for t in transactions
            ]
        }

    async def _get_transaction_or_raise(
        self, provider_transaction_id: str
    ) -> ProviderTransaction:
        transaction = await self._transactions.get_by_provider_transaction_id(
            provider="PAYME", provider_transaction_id=provider_transaction_id
        )
        if transaction is None:
            raise PaymeError(ERR_TRANSACTION_NOT_FOUND, "Transaction not found")
        return transaction


def _create_transaction_response(transaction: ProviderTransaction) -> dict[str, Any]:
    return {
        "create_time": _to_ms(transaction.created_at),
        "transaction": str(transaction.id),
        "state": _payme_state(transaction),
    }


def _perform_transaction_response(transaction: ProviderTransaction) -> dict[str, Any]:
    return {
        "transaction": str(transaction.id),
        "perform_time": _to_ms(transaction.performed_at),
        "state": _payme_state(transaction),
    }


def _cancel_transaction_response(transaction: ProviderTransaction) -> dict[str, Any]:
    return {
        "transaction": str(transaction.id),
        "cancel_time": _to_ms(transaction.cancelled_at),
        "state": _payme_state(transaction),
    }


def _check_transaction_response(transaction: ProviderTransaction) -> dict[str, Any]:
    return {
        "create_time": _to_ms(transaction.created_at),
        "perform_time": _to_ms(transaction.performed_at),
        "cancel_time": _to_ms(transaction.cancelled_at),
        "transaction": str(transaction.id),
        "state": _payme_state(transaction),
        "reason": int(transaction.cancel_reason)
        if transaction.cancel_reason and transaction.cancel_reason.isdigit()
        else None,
    }


@dataclass(frozen=True)
class PaymeAccount:
    """Unused by the handler above (which reads `params["account"]` as a plain dict) -- kept as
    the documented, typed shape of what Payme's merchant cabinet must be configured to send, for
    anyone wiring the cabinet's "Kassa hisobga olish maydoni" (account field) settings."""

    invoice_id: UUID
