"""billing -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from billing.interfaces.dto import (
    Entitlement,
    Invoice,
    InvoicePage,
    Order,
    OrderCreateRequest,
    OrderPage,
    PaymentConfirmationRequest,
    Product,
)


class OrderPort(Protocol):
    """Derived from OpenAPI operations: `adminListInvoices`, `confirmInvoicePayment`, `createOrder`, `getOrder`, `getOrderInvoice`, `listMyEntitlements`, `listMyOrders`, `listProducts`."""

    async def admin_list_invoices(
        self,
        status: Literal["ISSUED", "PAID", "VOID"] | None = None,
        cursor: str | None = None,
        limit: int | None = 20,
    ) -> InvoicePage:
        """`GET /admin/billing/invoices` (operationId `adminListInvoices`). List invoices (admin)"""
        ...

    async def confirm_invoice_payment(
        self, invoice_id: UUID, body: PaymentConfirmationRequest
    ) -> Invoice:
        """`POST /admin/billing/invoices/{invoiceId}/confirm-payment` (operationId `confirmInvoicePayment`). Confirm offline payment"""
        ...

    async def create_order(self, body: OrderCreateRequest) -> Order:
        """`POST /orders` (operationId `createOrder`). Place a purchase order"""
        ...

    async def get_order(self, order_id: UUID) -> Order:
        """`GET /orders/{orderId}` (operationId `getOrder`). Get an order"""
        ...

    async def get_order_invoice(self, order_id: UUID) -> Invoice:
        """`GET /orders/{orderId}/invoice` (operationId `getOrderInvoice`). Get the invoice for an order"""
        ...

    async def list_my_entitlements(self, active_only: bool | None = True) -> list[Entitlement]:
        """`GET /me/entitlements` (operationId `listMyEntitlements`). List my active entitlements"""
        ...

    async def list_my_orders(self, cursor: str | None = None, limit: int | None = 20) -> OrderPage:
        """`GET /orders` (operationId `listMyOrders`). List my orders"""
        ...

    async def list_products(
        self,
        product_type: Literal[
            "SUBSCRIPTION",
            "PREMIUM",
            "FEATURED",
            "TOP_PLACEMENT",
            "VERIFICATION",
            "BANNER_PLACEMENT",
        ]
        | None = None,
    ) -> list[Product]:
        """`GET /products` (operationId `listProducts`). List products & subscription plans"""
        ...


class PaymentProviderPort(Protocol):
    """SAD Sec 7.2 lists this on billing's public interface row. Offline in v1 (DEC-02): the only
    adapter is manual/offline confirmation, reached through the same confirmInvoicePayment HTTP
    operation modelled on OrderPort, not a separate REST surface. Kept as a named marker because
    v2 online providers (Click, Payme, Uzum, Freedom Pay, Stripe) attach here without changing
    OrderPort."""
