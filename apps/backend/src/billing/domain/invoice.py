"""billing -- the `Invoice` aggregate (DDD Sec 5.8 `AR: Invoice [P]`). The offline billing
document (DEC-02, BRULE-14): "settled offline in v1." Append-only financial record -- Physical DB
Design's own text: "corrections by VOID + new invoice, never by edit." `confirm_payment` is the
Invoice-side half of the sanctioned synchronous transaction (DB Architecture Sec 1.3).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from billing.domain.exceptions import IllegalInvoiceStateTransitionError
from billing.domain.value_objects import InvoiceStatus, PaymentConfirmation
from shared_kernel import Money


@dataclass(frozen=True)
class Invoice:
    id: UUID
    order_id: UUID
    invoice_number: str
    """Human-readable business code (DB Architecture Sec 10 "Business Code"), formatted from
    `billing.invoice_number_seq` -- assigned only at issue, never reused, never renumbered on
    correction (a voided invoice keeps its own number; a replacement invoice gets the next one)."""
    amount: Money
    status: InvoiceStatus
    payment_confirmation: PaymentConfirmation | None
    issued_at: datetime
    updated_at: datetime
    lock_version: int = 0

    @staticmethod
    def issue(
        *, invoice_id: UUID, order_id: UUID, invoice_number: str, amount: Money, now: datetime
    ) -> Invoice:
        """FR-BILL-001. One invoice per order in v1 (Domain Model Sec 5.8: "1 ↔ 1 Order")."""
        return Invoice(
            id=invoice_id,
            order_id=order_id,
            invoice_number=invoice_number,
            amount=amount,
            status=InvoiceStatus.ISSUED,
            payment_confirmation=None,
            issued_at=now,
            updated_at=now,
        )

    def confirm_payment(self, *, confirmed_by: UUID, note: str | None, now: datetime) -> Invoice:
        """FR-BILL-002/I-14: "an administrator confirms offline payment." `ISSUED -> PAID` only
        -- the sanctioned synchronous transaction's Invoice-side half; `application.
        payment_use_cases.PaymentUseCases.confirm_payment` calls this, `Order.mark_paid`, and
        `EntitlementFactory.activate_from_paid_order` together in one transaction."""
        if self.status is not InvoiceStatus.ISSUED:
            raise IllegalInvoiceStateTransitionError("confirm_payment", self.status.value)
        confirmation = PaymentConfirmation(confirmed_by=confirmed_by, confirmed_at=now, note=note)
        return replace(
            self, status=InvoiceStatus.PAID, payment_confirmation=confirmation, updated_at=now
        )

    def void(self, *, now: datetime) -> Invoice:
        """`ISSUED -> VOID` only (Domain Model Sec 5.8's own state diagram: `Issued -> Paid |
        Void`, both terminal, both reachable only from `Issued`) -- a `PAID` invoice is never
        voided directly; correcting a paid invoice is a business process outside this task's
        scope (no document names one). No use case in this task calls `void` (no OpenAPI
        operation exposes it); provided for lifecycle completeness, matching `Order.fulfill`'s
        own "capability exists, no caller wires it yet" note."""
        if self.status is not InvoiceStatus.ISSUED:
            raise IllegalInvoiceStateTransitionError("void", self.status.value)
        return replace(self, status=InvoiceStatus.VOID, updated_at=now)
