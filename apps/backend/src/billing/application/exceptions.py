"""billing/application -- exceptions for facts the domain layer cannot know (I/O failures,
missing configuration, not-found lookups). Mirrors `catalog.application.exceptions`'s style."""

from __future__ import annotations

from uuid import UUID


class BillingApplicationError(Exception):
    """Base for every typed exception raised by billing's application/ layer."""


class NoActingProfileError(BillingApplicationError):
    """`createOrder`/`listMyOrders`/`getOrder`/`listMyEntitlements` were called with no acting
    business profile (`X-Acting-Profile` omitted or the session's personal context) --
    `Order.purchaserProfileId` is a required, never-nullable OpenAPI field (every v1 purchase is
    business-profile-scoped, Baseline: "every source is a business paying the platform"). Maps to
    422, not 403: this is a malformed request, not a permission denial."""


class ProductNotFoundError(BillingApplicationError):
    """The referenced `ProductDefinition` has no published, current version -- fails closed
    (DEC-21: never invent a price/term)."""

    def __init__(self, product_id: UUID) -> None:
        self.product_id = product_id
        super().__init__(f"no published product definition {product_id}")


class OrderNotFoundError(BillingApplicationError):
    def __init__(self, order_id: UUID) -> None:
        self.order_id = order_id
        super().__init__(f"no order {order_id}")


class EntitlementNotFoundError(BillingApplicationError):
    def __init__(self, entitlement_id: UUID) -> None:
        self.entitlement_id = entitlement_id
        super().__init__(f"no entitlement {entitlement_id}")


class InvoiceNotFoundError(BillingApplicationError):
    def __init__(self, invoice_id: UUID | None = None, *, order_id: UUID | None = None) -> None:
        self.invoice_id = invoice_id
        self.order_id = order_id
        target = f"invoice {invoice_id}" if invoice_id else f"invoice for order {order_id}"
        super().__init__(f"no {target}")


class NotOrderPurchaserError(BillingApplicationError):
    """`getOrder`/`getOrderInvoice`'s own ownership check: the caller is neither the account nor
    the acting business profile that placed the order. Maps to 403 `PERMISSION_DENIED` -- an
    ownership check, not an `AuthorizationPort` gate (self-service scope, mirroring
    `catalog.application.exceptions.NotListingOwnerError`)."""

    def __init__(self, order_id: UUID) -> None:
        self.order_id = order_id
        super().__init__(f"caller does not own order {order_id}")


class PaymentNotConfirmedError(BillingApplicationError):
    """The operator submitted `PaymentConfirmationRequest.confirmed=false` (or the configured
    `PaymentProviderPort` otherwise declined) -- the invoice stays `ISSUED`, no state changes."""

    def __init__(self, invoice_id: UUID) -> None:
        self.invoice_id = invoice_id
        super().__init__(f"payment for invoice {invoice_id} was not confirmed")
