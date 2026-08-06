"""billing/application -- `PaymentUseCases` (Task P-09): `confirmInvoicePayment`/
`adminListInvoices`. `confirm_payment` is THE sanctioned synchronous multi-aggregate transaction
(DB Architecture Sec 1.3: "Invoice→Paid + Order→Paid + Entitlement activation, all inside one
BC-08 transaction") -- an explicit, documented exception to "one aggregate per transaction"
(ABSOLUTE ARCHITECTURE RULE 7), confined to this one method, in this one context, never
generalised elsewhere in this module or repeated in any other. The three repositories +
`OutboxPort` this method calls all share the one `AsyncSession` the composition root binds them
to (`infrastructure/persistence/repository.py`'s three classes are always constructed against the
same session in `composition_root.provide_payment_use_cases`) -- there is no separate commit call
anywhere in this method; the caller's own transaction boundary commits everything together or
rolls all of it back.

I-14 itself ("an Entitlement activates only upon administrator-confirmed payment") is enforced
TWICE, deliberately redundantly: `EntitlementFactory.activate_from_paid_order`'s own structural
guard (raises unless `order.status is PAID`, `billing/domain/entitlement.py`) is the real,
load-bearing check; this method's own ordering -- mark the order `PAID` *before* calling the
factory -- is what makes that guard's precondition true by construction, not by hoping the
caller got the order right.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from billing.application.exceptions import (
    InvoiceNotFoundError,
    OrderNotFoundError,
    PaymentNotConfirmedError,
)
from billing.application.ports import (
    EntitlementRepository,
    InvoiceRepository,
    OrderRepository,
    PaymentProviderPort,
)
from billing.domain import Entitlement, EntitlementFactory, Invoice, Order
from contracts.events.billing import EntitlementActivated, PaymentConfirmed
from shared_kernel import OutboxPort


class PaymentUseCases:
    def __init__(
        self,
        *,
        orders: OrderRepository,
        invoices: InvoiceRepository,
        entitlements: EntitlementRepository,
        payment_provider: PaymentProviderPort,
        outbox: OutboxPort,
    ) -> None:
        self._orders = orders
        self._invoices = invoices
        self._entitlements = entitlements
        self._payment_provider = payment_provider
        self._outbox = outbox

    async def confirm_payment(
        self,
        *,
        invoice_id: UUID,
        operator_account_id: UUID,
        confirmed: bool,
        note: str | None,
        now: datetime,
    ) -> Invoice:
        invoice = await self._invoices.get_by_id(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(invoice_id)
        order = await self._orders.get_by_id(invoice.order_id)
        if order is None:
            raise OrderNotFoundError(invoice.order_id)

        should_confirm = await self._payment_provider.confirm(
            invoice_id=invoice_id,
            confirmed=confirmed,
            operator_account_id=operator_account_id,
            note=note,
        )
        if not should_confirm:
            raise PaymentNotConfirmedError(invoice_id)

        invoice = invoice.confirm_payment(confirmed_by=operator_account_id, note=note, now=now)
        invoice = await self._invoices.save(invoice)

        order = order.mark_paid(now=now)
        order = await self._orders.save(order)

        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=now
        )
        await self._entitlements.add(entitlement)

        await self._outbox.append(
            PaymentConfirmed(
                event_id=uuid4(),
                occurred_at=now,
                actor=operator_account_id,
                aggregate_type="Invoice",
                aggregate_id=invoice.id,
                payload=_payment_confirmed_payload(invoice, order),
            )
        )
        await self._outbox.append(
            EntitlementActivated(
                event_id=uuid4(),
                occurred_at=now,
                actor=operator_account_id,
                aggregate_type="Entitlement",
                aggregate_id=entitlement.id,
                payload=_entitlement_activated_payload(entitlement, order),
            )
        )
        return invoice

    async def admin_list_invoices(
        self, *, status: str | None, cursor: str | None, limit: int
    ) -> tuple[list[Invoice], str | None]:
        return await self._invoices.list_all(status=status, cursor=cursor, limit=limit)


def _payment_confirmed_payload(invoice: Invoice, order: Order) -> dict[str, object]:
    return {
        "invoiceId": str(invoice.id),
        "orderId": str(order.id),
        "purchaserProfileId": str(order.purchaser_profile_id.value),
        "amount": str(invoice.amount.amount),
        "currency": invoice.amount.currency,
    }


def _entitlement_activated_payload(entitlement: Entitlement, order: Order) -> dict[str, object]:
    """Deliberately rich: one `EntitlementActivated` event type serves all four
    `EntitlementType`s (Domain Model Sec 5.8), and the already-built downstream consumers each
    read a different subset of fields -- `catalog.infrastructure.event_projection.
    handle_entitlement_event` (`ownerProfileId`/`entitlementId`/`validUntil`/
    `productDefinitionId`/`quota`, subscription-quota projection) and `search.infrastructure.
    event_projection.handle_entitlement_activated` (`listingId`/`kind`/`entitlementId`/
    `validUntil`, promotion projection). Both are satisfied by this ONE payload shape; the
    composition root routes the event to only the relevant consumer per `entitlementType`
    (see `composition_root.py`'s own billing wiring section) -- neither consumer discriminates by
    type internally, so misrouting a `LISTING_PROMOTION` event into catalog's handler would
    silently corrupt that profile's subscription snapshot, and misrouting an
    `ACTIVE_SUBSCRIPTION` event into search's handler would raise `MalformedEventPayloadError`
    (no `listingId` to find)."""
    is_promotion = entitlement.promotion_kind is not None
    return {
        "entitlementId": str(entitlement.id),
        "orderId": str(order.id),
        "entitlementType": entitlement.entitlement_type.value,
        "ownerProfileId": str(order.purchaser_profile_id.value),
        "targetId": str(entitlement.target_id),
        "listingId": str(entitlement.target_id) if is_promotion else None,
        "kind": entitlement.promotion_kind.value if entitlement.promotion_kind else None,
        "productDefinitionId": str(order.product_snapshot.product_definition_id),
        "quota": order.product_snapshot.quota,
        "validFrom": entitlement.valid_from.isoformat(),
        "validUntil": entitlement.valid_until.isoformat(),
    }
