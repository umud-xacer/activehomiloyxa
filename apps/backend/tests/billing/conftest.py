"""Shared fixtures for `billing`'s fast (no-DB) unit + API tests: in-memory fakes for every port
`application/ports.py` declares, mirroring `apps/backend/tests/catalog/conftest.py`'s pattern
exactly."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import pytest

from billing.application.ports import ProductDefinitionSnapshot
from billing.domain import Entitlement, Invoice, Order, ProductType
from shared_kernel import EventEnvelope, LocalizedText


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id)


@dataclass
class FakeOrderRepository:
    """Implements `billing.application.ports.OrderRepository`."""

    orders: dict[UUID, Order] = field(default_factory=dict)

    async def get_by_id(self, order_id: UUID) -> Order | None:
        return self.orders.get(order_id)

    async def add(self, order: Order) -> None:
        self.orders[order.id] = order

    async def save(self, order: Order) -> Order:
        self.orders[order.id] = order
        return order

    async def list_by_purchaser(
        self, purchaser_profile_id: UUID, *, cursor: str | None, limit: int
    ) -> tuple[list[Order], str | None]:
        items = sorted(
            (
                o
                for o in self.orders.values()
                if o.purchaser_profile_id.value == purchaser_profile_id
            ),
            key=lambda o: (o.created_at, o.id),
        )
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            items = [i for i in items if (i.created_at, i.id) > (created_at, row_id)]
        page = items[: limit + 1]
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = _encode_cursor(page[-1].created_at, page[-1].id)
        return page, next_cursor


@dataclass
class FakeInvoiceRepository:
    """Implements `billing.application.ports.InvoiceRepository`."""

    invoices: dict[UUID, Invoice] = field(default_factory=dict)
    _next_seq: int = 1

    async def get_by_id(self, invoice_id: UUID) -> Invoice | None:
        return self.invoices.get(invoice_id)

    async def get_by_order_id(self, order_id: UUID) -> Invoice | None:
        for invoice in self.invoices.values():
            if invoice.order_id == order_id:
                return invoice
        return None

    async def add(self, invoice: Invoice) -> None:
        self.invoices[invoice.id] = invoice

    async def save(self, invoice: Invoice) -> Invoice:
        self.invoices[invoice.id] = invoice
        return invoice

    async def list_all(
        self, *, status: str | None, cursor: str | None, limit: int
    ) -> tuple[list[Invoice], str | None]:
        items = sorted(self.invoices.values(), key=lambda i: (i.issued_at, i.id))
        if status is not None:
            items = [i for i in items if i.status.value == status]
        if cursor is not None:
            issued_at, row_id = _decode_cursor(cursor)
            items = [i for i in items if (i.issued_at, i.id) > (issued_at, row_id)]
        page = items[: limit + 1]
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = _encode_cursor(page[-1].issued_at, page[-1].id)
        return page, next_cursor

    async def next_invoice_number(self) -> str:
        number = f"INV-{self._next_seq:06d}"
        self._next_seq += 1
        return number


@dataclass
class FakeEntitlementRepository:
    """Implements `billing.application.ports.EntitlementRepository`. `orders` is a SHARED
    reference to a `FakeOrderRepository.orders` dict (injected by the `fake_entitlements`
    fixture) -- mirrors `SqlalchemyEntitlementRepository.list_active_for_profile`'s own real
    `JOIN purchase_order` (an entitlement's `target_id` is the BENEFIT target -- a listing id for
    `LISTING_PROMOTION` -- never the purchaser; only the order it was activated from knows who
    purchased it)."""

    entitlements: dict[UUID, Entitlement] = field(default_factory=dict)
    orders: dict[UUID, Order] = field(default_factory=dict)

    async def get_by_id(self, entitlement_id: UUID) -> Entitlement | None:
        return self.entitlements.get(entitlement_id)

    async def add(self, entitlement: Entitlement) -> None:
        self.entitlements[entitlement.id] = entitlement

    async def save(self, entitlement: Entitlement) -> Entitlement:
        self.entitlements[entitlement.id] = entitlement
        return entitlement

    async def list_by_order_id(self, order_id: UUID) -> tuple[Entitlement, ...]:
        return tuple(e for e in self.entitlements.values() if e.order_id == order_id)

    async def list_active_for_profile(
        self, purchaser_profile_id: UUID, *, active_only: bool
    ) -> tuple[Entitlement, ...]:
        result = []
        for entitlement in self.entitlements.values():
            order = self.orders.get(entitlement.order_id)
            if order is None or order.purchaser_profile_id.value != purchaser_profile_id:
                continue
            if active_only and entitlement.activation_state.value != "ACTIVE":
                continue
            result.append(entitlement)
        return tuple(result)

    async def list_expiring_active(
        self, *, now: datetime, batch_size: int
    ) -> tuple[Entitlement, ...]:
        result = [
            e
            for e in self.entitlements.values()
            if e.activation_state.value == "ACTIVE" and e.valid_until <= now
        ]
        result.sort(key=lambda e: e.valid_until)
        return tuple(result[:batch_size])


class FakeProductDefinitionReaderPort:
    """Implements `billing.application.ports.ProductDefinitionReaderPort`."""

    def __init__(self) -> None:
        self.products: dict[UUID, ProductDefinitionSnapshot] = {}

    def seed(self, **overrides: object) -> ProductDefinitionSnapshot:
        from uuid import uuid4

        defaults: dict[str, object] = {
            "id": uuid4(),
            "version_id": uuid4(),
            "code": "premium-30d",
            "product_type": ProductType.PREMIUM,
            "name": LocalizedText(uz_latn="Premium"),
            "description": None,
            "price_amount": "50000.00",
            "price_currency": "UZS",
            "term_days": 30,
            "quota": None,
        }
        defaults.update(overrides)
        product = ProductDefinitionSnapshot(**defaults)  # type: ignore[arg-type]
        self.products[product.id] = product
        return product

    async def get_product(self, product_id: UUID) -> ProductDefinitionSnapshot | None:
        return self.products.get(product_id)

    async def list_products(
        self, *, product_type: ProductType | None
    ) -> tuple[ProductDefinitionSnapshot, ...]:
        items = list(self.products.values())
        if product_type is not None:
            items = [p for p in items if p.product_type is product_type]
        return tuple(items)


class FakePaymentProviderPort:
    """Implements `billing.application.ports.PaymentProviderPort`. Mirrors
    `OfflineManualPaymentAdapter`'s own behaviour (returns `confirmed` verbatim) by default;
    tests may override `.always_confirm`/`.always_decline` for a v2-provider-shaped scenario."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def confirm(
        self, *, invoice_id: UUID, confirmed: bool, operator_account_id: UUID, note: str | None
    ) -> bool:
        self.calls.append(
            {
                "invoice_id": invoice_id,
                "confirmed": confirmed,
                "operator_account_id": operator_account_id,
                "note": note,
            }
        )
        return confirmed


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


@pytest.fixture
def fake_orders() -> FakeOrderRepository:
    return FakeOrderRepository()


@pytest.fixture
def fake_invoices() -> FakeInvoiceRepository:
    return FakeInvoiceRepository()


@pytest.fixture
def fake_entitlements(fake_orders: FakeOrderRepository) -> FakeEntitlementRepository:
    return FakeEntitlementRepository(orders=fake_orders.orders)


@pytest.fixture
def fake_products() -> FakeProductDefinitionReaderPort:
    return FakeProductDefinitionReaderPort()


@pytest.fixture
def fake_payment_provider() -> FakePaymentProviderPort:
    return FakePaymentProviderPort()


@pytest.fixture
def fake_outbox() -> FakeOutbox:
    return FakeOutbox()
