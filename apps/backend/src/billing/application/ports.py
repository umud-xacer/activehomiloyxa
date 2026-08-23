"""billing/application -- ports (Task P-09). Abstract surface only (typing.Protocol);
`infrastructure/` implements every one of these, never the reverse (Clean Architecture rule 4).

Every cross-module read is shaped as billing's *own* narrow Protocol/dataclass here -- never a
`configuration.interfaces` type imported directly -- the same discipline `catalog.application.
ports.CategoryFormPort`/`CategorySnapshot` already set (P-07). The concrete adapter bridging to
`configuration.interfaces` lives in `billing/infrastructure/`, wired only at the composition root
(`cross-module-billing`, tools/importlinter.cfg).

`PaymentProviderPort` here -- NOT `billing.interfaces.ports.PaymentProviderPort` (the frozen P-01
marker stub, which declares no methods at all) -- is the real, callable v2 seam (FR-BILL-004,
BRULE-15): `PaymentUseCases.confirm_payment` depends on this Protocol, never on
`OfflineManualPaymentAdapter` directly, so a v2 online-provider adapter attaches here without
touching `application`/`domain`. The frozen `interfaces.ports.PaymentProviderPort` stays untouched
scaffolding, exactly like `search.interfaces.ports.SearchQueryPort`/`catalog.interfaces.ports.
ListingPort` -- P-01 Protocols this codebase's precedent never actually implements.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from billing.domain import Entitlement, Invoice, Order, ProductType
from shared_kernel import LocalizedText


class OrderRepository(Protocol):
    """One repository per aggregate root (`Order`) -- Clean Architecture rule 2."""

    async def get_by_id(self, order_id: UUID) -> Order | None: ...

    async def add(self, order: Order) -> None: ...

    async def save(self, order: Order) -> Order:
        """Returns the persisted aggregate with its post-flush `lock_version` -- callers must use
        the returned value (mirrors `catalog.application.ports.ListingRepository.save`)."""
        ...

    async def list_by_purchaser(
        self, purchaser_profile_id: UUID, *, cursor: str | None, limit: int
    ) -> tuple[list[Order], str | None]:
        """Backs `listMyOrders`. Returns `(orders, next_cursor)`."""
        ...


class InvoiceRepository(Protocol):
    """One repository per aggregate root (`Invoice`)."""

    async def get_by_id(self, invoice_id: UUID) -> Invoice | None: ...

    async def get_by_order_id(self, order_id: UUID) -> Invoice | None:
        """One invoice per order in v1 (Domain Model Sec 5.8 "1 ↔ 1 Order")."""
        ...

    async def add(self, invoice: Invoice) -> None: ...

    async def save(self, invoice: Invoice) -> Invoice: ...

    async def list_all(
        self, *, status: str | None, cursor: str | None, limit: int
    ) -> tuple[list[Invoice], str | None]:
        """Backs `adminListInvoices` -- the billing-operator queue, unscoped by purchaser."""
        ...

    async def next_invoice_number(self) -> str:
        """`billing.invoice_number_seq` (Physical DB Design) -- formatted, sequential, assigned
        only at issue (FR-BILL-003). The adapter owns the exact format; this port only promises
        "unique, assigned once, never reused"."""
        ...


class EntitlementRepository(Protocol):
    """One repository per aggregate root (`Entitlement`)."""

    async def get_by_id(self, entitlement_id: UUID) -> Entitlement | None: ...

    async def add(self, entitlement: Entitlement) -> None: ...

    async def save(self, entitlement: Entitlement) -> Entitlement: ...

    async def list_by_order_id(self, order_id: UUID) -> tuple[Entitlement, ...]: ...

    async def list_active_for_profile(
        self, purchaser_profile_id: UUID, *, active_only: bool
    ) -> tuple[Entitlement, ...]:
        """Backs `listMyEntitlements`. `active_only=False` also returns `EXPIRED`/`REVOKED` rows
        for the same profile -- the OpenAPI `activeOnly` query parameter, default `true`."""
        ...

    async def list_expiring_active(
        self, *, now: datetime, batch_size: int
    ) -> tuple[Entitlement, ...]:
        """Backs the expiry sweep (FR-SUBS-004): every `ACTIVE` entitlement whose `valid_until`
        is at or before `now`, oldest first, capped at `batch_size` per sweep batch (mirrors
        `catalog.application.ports.ListingRepository.list_expiring`'s own shape)."""
        ...


@dataclass(frozen=True)
class ProductDefinitionSnapshot:
    """billing's own narrow read shape for a configured `ProductDefinition`
    (`configuration.domain.content.ProductDefinitionContent`) -- not a
    `configuration.interfaces` DTO. `code`/`name`/`description` come from the owning
    `ConfigurationHead`/`ConfigDescriptor`, not the version content itself (`listProducts`'s own
    `Product` DTO needs all three)."""

    id: UUID
    version_id: UUID
    code: str
    product_type: ProductType
    name: LocalizedText
    description: LocalizedText | None
    price_amount: str
    """Decimal-as-string (`configuration.domain.content.ProductDefinitionContent.price_amount`'s
    own wire shape) -- the adapter converts to `Decimal` when building the frozen
    `ProductSnapshot`, matching every other module's Money-from-config-snapshot precedent."""
    price_currency: str
    term_days: int | None
    quota: dict[str, object] | None
    category_id: UUID | None = None
    """`LISTING_PUBLICATION` products only (2026-08-23, listing paywall): `None` is the
    platform-default single-listing price; a specific category's override otherwise."""


class ProductDefinitionReaderPort(Protocol):
    """Reads the published `ProductDefinition` snapshot from `configuration` (I-07's frozen-at-
    order-time source). The concrete adapter calls `configuration.interfaces.ports.
    ConfigurationPort.list_config_heads`/`get_config_version` only -- never `configuration.
    domain`/`application`/`infrastructure` (`cross-module-billing`)."""

    async def get_product(
        self, product_id: UUID
    ) -> ProductDefinitionSnapshot | None: ...

    async def list_products(
        self, *, product_type: ProductType | None
    ) -> tuple[ProductDefinitionSnapshot, ...]:
        """Backs the public `listProducts` operation."""
        ...


class PaymentProviderPort(Protocol):
    """FR-BILL-004/BRULE-15: "the billing capability SHALL be structured so online providers can
    be added in v2 without changing business logic." `PaymentUseCases.confirm_payment` depends on
    this Protocol only; it never knows which concrete adapter is registered."""

    async def confirm(
        self,
        *,
        invoice_id: UUID,
        confirmed: bool,
        operator_account_id: UUID,
        note: str | None,
    ) -> bool:
        """Returns whether this attempt should transition the invoice to `PAID`. v1's
        `OfflineManualPaymentAdapter` returns `confirmed` verbatim: the operator's own HTTP-level
        attestation *is* the confirmation in an offline flow, with no external gateway to
        consult. A v2 online-provider adapter would instead verify a referenced provider
        transaction here -- unused in v1."""
        ...
