"""billing/domain -- the `Order`/`Invoice`/`Entitlement` aggregates, value objects, the
`EntitlementFactory` (I-14's structural guard), and typed domain exceptions (Task P-09). Imports
`shared_kernel` only (Clean Architecture rule 1); never imported by another module (`domain/` is
never part of a module's public surface, AIR-02)."""

from __future__ import annotations

from billing.domain.entitlement import Entitlement, EntitlementFactory
from billing.domain.exceptions import (
    BillingDomainError,
    EntitlementActivationWithoutPaymentError,
    IllegalEntitlementStateTransitionError,
    IllegalInvoiceStateTransitionError,
    IllegalOrderStateTransitionError,
    InvalidTargetRefError,
    MissingTermError,
    TargetTypeMismatchError,
    UnsupportedProductTypeError,
)
from billing.domain.invoice import Invoice
from billing.domain.order import Order
from billing.domain.product_mapping import (
    ENTITLEMENT_TYPE_BY_PRODUCT,
    PROMOTION_KIND_BY_PRODUCT,
    REQUIRED_TARGET_TYPE_BY_PRODUCT,
)
from billing.domain.value_objects import (
    ActivationState,
    EntitlementType,
    InvoiceStatus,
    OrderStatus,
    PaymentConfirmation,
    ProductSnapshot,
    ProductType,
    PromotionKind,
    TargetRef,
    TargetType,
)

__all__ = [
    "ENTITLEMENT_TYPE_BY_PRODUCT",
    "PROMOTION_KIND_BY_PRODUCT",
    "REQUIRED_TARGET_TYPE_BY_PRODUCT",
    "ActivationState",
    "BillingDomainError",
    "Entitlement",
    "EntitlementActivationWithoutPaymentError",
    "EntitlementFactory",
    "EntitlementType",
    "IllegalEntitlementStateTransitionError",
    "IllegalInvoiceStateTransitionError",
    "IllegalOrderStateTransitionError",
    "InvalidTargetRefError",
    "Invoice",
    "InvoiceStatus",
    "MissingTermError",
    "Order",
    "OrderStatus",
    "PaymentConfirmation",
    "ProductSnapshot",
    "ProductType",
    "PromotionKind",
    "TargetRef",
    "TargetType",
    "TargetTypeMismatchError",
    "UnsupportedProductTypeError",
]
