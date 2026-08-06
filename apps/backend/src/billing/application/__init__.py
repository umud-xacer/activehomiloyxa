"""billing/application -- use cases + ports (Task P-09). Depends only on `billing.domain` and
`shared_kernel` -- never `billing.interfaces` (`layers-billing`, tools/importlinter.cfg)."""

from __future__ import annotations

from billing.application.entitlement_use_cases import EntitlementUseCases
from billing.application.exceptions import (
    BillingApplicationError,
    EntitlementNotFoundError,
    InvoiceNotFoundError,
    NoActingProfileError,
    NotOrderPurchaserError,
    OrderNotFoundError,
    PaymentNotConfirmedError,
    ProductNotFoundError,
)
from billing.application.order_use_cases import OrderUseCases
from billing.application.payment_use_cases import PaymentUseCases
from billing.application.ports import (
    EntitlementRepository,
    InvoiceRepository,
    OrderRepository,
    PaymentProviderPort,
    ProductDefinitionReaderPort,
    ProductDefinitionSnapshot,
)

__all__ = [
    "BillingApplicationError",
    "EntitlementNotFoundError",
    "EntitlementRepository",
    "EntitlementUseCases",
    "InvoiceNotFoundError",
    "InvoiceRepository",
    "NoActingProfileError",
    "NotOrderPurchaserError",
    "OrderNotFoundError",
    "OrderRepository",
    "OrderUseCases",
    "PaymentNotConfirmedError",
    "PaymentProviderPort",
    "PaymentUseCases",
    "ProductDefinitionReaderPort",
    "ProductDefinitionSnapshot",
    "ProductNotFoundError",
]
