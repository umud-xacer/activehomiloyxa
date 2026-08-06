"""billing/application -- `OrderUseCases` (Task P-09): `createOrder`/`getOrder`/`listMyOrders`/
`listProducts`. FR-SUBS-001/002, I-07 (ProductSnapshot frozen at order time).

`create_order` also issues the order's invoice in the same call (FR-BILL-001: "generate an
invoice for each purchase order" -- no separate OpenAPI operation exists to do this later, and
"1 ↔ 1 Order" makes eager issuance the only design that gives `getOrderInvoice` something to
return immediately after `createOrder` returns)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from billing.application.exceptions import (
    NotOrderPurchaserError,
    OrderNotFoundError,
    ProductNotFoundError,
)
from billing.application.ports import (
    InvoiceRepository,
    OrderRepository,
    ProductDefinitionReaderPort,
    ProductDefinitionSnapshot,
)
from billing.domain import Invoice, Order, ProductSnapshot, ProductType, TargetRef, TargetType
from contracts.events.billing import InvoiceIssued, OrderPlaced
from shared_kernel import BusinessProfileId, Money, OutboxPort


class OrderUseCases:
    def __init__(
        self,
        *,
        orders: OrderRepository,
        invoices: InvoiceRepository,
        products: ProductDefinitionReaderPort,
        outbox: OutboxPort,
    ) -> None:
        self._orders = orders
        self._invoices = invoices
        self._products = products
        self._outbox = outbox

    async def create_order(
        self,
        *,
        purchaser_profile_id: BusinessProfileId,
        product_id: UUID,
        target_type: TargetType,
        target_id: UUID | None,
        booking_window: tuple[datetime, datetime] | None,
        now: datetime,
    ) -> Order:
        product = await self._products.get_product(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)

        snapshot = _to_product_snapshot(product)
        target = TargetRef(
            target_type=target_type, target_id=target_id, booking_window=booking_window
        )

        order = Order.create(
            order_id=uuid4(),
            purchaser_profile_id=purchaser_profile_id,
            product_snapshot=snapshot,
            target=target,
            now=now,
        )
        await self._orders.add(order)
        await self._outbox.append(
            OrderPlaced(
                event_id=uuid4(),
                occurred_at=now,
                actor=purchaser_profile_id.value,
                aggregate_type="Order",
                aggregate_id=order.id,
                payload=_order_payload(order),
            )
        )

        invoice_number = await self._invoices.next_invoice_number()
        invoice = Invoice.issue(
            invoice_id=uuid4(),
            order_id=order.id,
            invoice_number=invoice_number,
            amount=order.amount,
            now=now,
        )
        await self._invoices.add(invoice)
        order = order.issue_invoice(now=now)
        order = await self._orders.save(order)
        await self._outbox.append(
            InvoiceIssued(
                event_id=uuid4(),
                occurred_at=now,
                actor=purchaser_profile_id.value,
                aggregate_type="Invoice",
                aggregate_id=invoice.id,
                payload=_invoice_payload(invoice),
            )
        )
        return order

    async def get_order(self, order_id: UUID, *, purchaser_profile_id: BusinessProfileId) -> Order:
        order = await self._orders.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        if order.purchaser_profile_id != purchaser_profile_id:
            raise NotOrderPurchaserError(order_id)
        return order

    async def list_my_orders(
        self, *, purchaser_profile_id: BusinessProfileId, cursor: str | None, limit: int
    ) -> tuple[list[Order], str | None]:
        return await self._orders.list_by_purchaser(
            purchaser_profile_id.value, cursor=cursor, limit=limit
        )

    async def list_products(
        self, *, product_type: ProductType | None
    ) -> tuple[ProductDefinitionSnapshot, ...]:
        return await self._products.list_products(product_type=product_type)

    async def get_order_invoice(self, order_id: UUID) -> Invoice | None:
        """`Order` (the domain aggregate) carries no `invoice_id` field -- the FK points the
        other way (`Invoice.order_id`, "the cheapest correct 1:1", `billing/domain/order.py`'s
        own note). Backs both `getOrderInvoice` and `interfaces/routers.py`'s own `Order.
        invoiceId` DTO field, which is nullable in the schema but in practice always resolves:
        `create_order` always issues the order's invoice in the same call, so no order this
        module ever persists is reachable via `getOrder`/`listMyOrders` without one."""
        return await self._invoices.get_by_order_id(order_id)


def _to_product_snapshot(product: ProductDefinitionSnapshot) -> ProductSnapshot:
    return ProductSnapshot(
        product_definition_id=product.id,
        product_definition_version_id=product.version_id,
        product_type=product.product_type,
        price=Money(amount=Decimal(product.price_amount), currency=product.price_currency),
        term_days=product.term_days,
        quota=product.quota,
    )


def _order_payload(order: Order) -> dict[str, object]:
    return {
        "orderId": str(order.id),
        "purchaserProfileId": str(order.purchaser_profile_id.value),
        "productDefinitionId": str(order.product_snapshot.product_definition_id),
        "productType": order.product_snapshot.product_type.value,
        "targetType": order.target.target_type.value,
        "targetId": str(order.target.target_id) if order.target.target_id else None,
        "amount": str(order.amount.amount),
        "currency": order.amount.currency,
        "status": order.status.value,
    }


def _invoice_payload(invoice: Invoice) -> dict[str, object]:
    return {
        "invoiceId": str(invoice.id),
        "orderId": str(invoice.order_id),
        "invoiceNumber": invoice.invoice_number,
        "amount": str(invoice.amount.amount),
        "currency": invoice.amount.currency,
        "status": invoice.status.value,
    }
