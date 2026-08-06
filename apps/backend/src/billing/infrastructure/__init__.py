"""billing/infrastructure -- SQLAlchemy repositories, the configuration adapter, the sole v1
`PaymentProviderPort` implementation, and the entitlement expiry sweep worker (Task P-09). Never
imported by `billing.interfaces`/`application`/`domain` -- only the composition root (outside
every module's package tree) wires these concrete classes behind the ports `application/`
declares."""

from __future__ import annotations

from billing.infrastructure.configuration_adapter import ConfigurationProductDefinitionAdapter
from billing.infrastructure.offline_payment_adapter import OfflineManualPaymentAdapter
from billing.infrastructure.persistence import (
    BillingBase,
    EntitlementRow,
    InvoiceRow,
    OutboxEventRow,
    ProcessedEventRow,
    PurchaseOrderRow,
    SqlalchemyEntitlementRepository,
    SqlalchemyInvoiceRepository,
    SqlalchemyOrderRepository,
)
from billing.infrastructure.worker import EntitlementExpiryWorker

__all__ = [
    "BillingBase",
    "ConfigurationProductDefinitionAdapter",
    "EntitlementExpiryWorker",
    "EntitlementRow",
    "InvoiceRow",
    "OfflineManualPaymentAdapter",
    "OutboxEventRow",
    "ProcessedEventRow",
    "PurchaseOrderRow",
    "SqlalchemyEntitlementRepository",
    "SqlalchemyInvoiceRepository",
    "SqlalchemyOrderRepository",
]
