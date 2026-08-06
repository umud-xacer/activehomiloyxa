"""`billing.application.order_use_cases.OrderUseCases` -- `create_order` (also eagerly issuing
the order's invoice, FR-BILL-001), `get_order`/`list_my_orders` (ownership scoping), and the
ProductSnapshot-frozen-at-order-time test (I-07) at the application layer."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from billing.application.exceptions import (
    NotOrderPurchaserError,
    OrderNotFoundError,
    ProductNotFoundError,
)
from billing.application.order_use_cases import OrderUseCases
from billing.domain import ProductType, TargetType
from shared_kernel import BusinessProfileId

from .conftest import (
    FakeInvoiceRepository,
    FakeOrderRepository,
    FakeOutbox,
    FakeProductDefinitionReaderPort,
)

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.fixture
def use_cases(
    fake_orders: FakeOrderRepository,
    fake_invoices: FakeInvoiceRepository,
    fake_products: FakeProductDefinitionReaderPort,
    fake_outbox: FakeOutbox,
) -> OrderUseCases:
    return OrderUseCases(
        orders=fake_orders, invoices=fake_invoices, products=fake_products, outbox=fake_outbox
    )


class TestCreateOrder:
    async def test_I01_creates_an_order_and_eagerly_issues_its_invoice(
        self,
        use_cases: OrderUseCases,
        fake_products: FakeProductDefinitionReaderPort,
        fake_invoices: FakeInvoiceRepository,
    ) -> None:
        product = fake_products.seed(product_type=ProductType.PREMIUM)
        purchaser = BusinessProfileId(value=uuid4())
        order = await use_cases.create_order(
            purchaser_profile_id=purchaser,
            product_id=product.id,
            target_type=TargetType.LISTING,
            target_id=uuid4(),
            booking_window=None,
            now=_NOW,
        )
        assert order.status.value == "INVOICED"
        invoice = await use_cases.get_order_invoice(order.id)
        assert invoice is not None
        assert invoice.order_id == order.id
        assert len(fake_invoices.invoices) == 1

    async def test_I02_unknown_product_raises(self, use_cases: OrderUseCases) -> None:
        with pytest.raises(ProductNotFoundError):
            await use_cases.create_order(
                purchaser_profile_id=BusinessProfileId(value=uuid4()),
                product_id=uuid4(),
                target_type=TargetType.LISTING,
                target_id=uuid4(),
                booking_window=None,
                now=_NOW,
            )

    async def test_I03_publishes_order_placed_then_invoice_issued(
        self,
        use_cases: OrderUseCases,
        fake_products: FakeProductDefinitionReaderPort,
        fake_outbox: FakeOutbox,
    ) -> None:
        product = fake_products.seed(product_type=ProductType.PREMIUM)
        await use_cases.create_order(
            purchaser_profile_id=BusinessProfileId(value=uuid4()),
            product_id=product.id,
            target_type=TargetType.LISTING,
            target_id=uuid4(),
            booking_window=None,
            now=_NOW,
        )
        assert [e.event_type for e in fake_outbox.events] == ["OrderPlaced", "InvoiceIssued"]

    async def test_I07_product_snapshot_is_frozen_at_order_creation(
        self, use_cases: OrderUseCases, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        """I-07, application layer: a later change to the SAME `ProductDefinitionSnapshot` object
        the fake reader returns must never retroactively alter an already-created order, because
        `create_order` copies every field it needs into the frozen `ProductSnapshot` at the
        moment of creation."""
        product = fake_products.seed(product_type=ProductType.PREMIUM, price_amount="50000.00")
        order = await use_cases.create_order(
            purchaser_profile_id=BusinessProfileId(value=uuid4()),
            product_id=product.id,
            target_type=TargetType.LISTING,
            target_id=uuid4(),
            booking_window=None,
            now=_NOW,
        )
        original_amount = order.amount

        # simulate a later configuration price change on the SAME product id.
        fake_products.seed(
            id=product.id,
            version_id=uuid4(),
            product_type=ProductType.PREMIUM,
            price_amount="999999.00",
        )

        refetched = await use_cases.get_order(
            order.id, purchaser_profile_id=order.purchaser_profile_id
        )
        assert refetched.amount == original_amount
        assert refetched.amount.amount == original_amount.amount


class TestGetOrder:
    async def test_ownership_check_denies_a_different_profile(
        self, use_cases: OrderUseCases, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        product = fake_products.seed(product_type=ProductType.PREMIUM)
        order = await use_cases.create_order(
            purchaser_profile_id=BusinessProfileId(value=uuid4()),
            product_id=product.id,
            target_type=TargetType.LISTING,
            target_id=uuid4(),
            booking_window=None,
            now=_NOW,
        )
        with pytest.raises(NotOrderPurchaserError):
            await use_cases.get_order(
                order.id, purchaser_profile_id=BusinessProfileId(value=uuid4())
            )

    async def test_not_found_raises(self, use_cases: OrderUseCases) -> None:
        with pytest.raises(OrderNotFoundError):
            await use_cases.get_order(
                uuid4(), purchaser_profile_id=BusinessProfileId(value=uuid4())
            )


class TestListMyOrders:
    async def test_only_returns_orders_for_the_given_purchaser(
        self, use_cases: OrderUseCases, fake_products: FakeProductDefinitionReaderPort
    ) -> None:
        product = fake_products.seed(product_type=ProductType.PREMIUM)
        mine = BusinessProfileId(value=uuid4())
        other = BusinessProfileId(value=uuid4())
        await use_cases.create_order(
            purchaser_profile_id=mine,
            product_id=product.id,
            target_type=TargetType.LISTING,
            target_id=uuid4(),
            booking_window=None,
            now=_NOW,
        )
        await use_cases.create_order(
            purchaser_profile_id=other,
            product_id=product.id,
            target_type=TargetType.LISTING,
            target_id=uuid4(),
            booking_window=None,
            now=_NOW,
        )
        orders, _cursor = await use_cases.list_my_orders(
            purchaser_profile_id=mine, cursor=None, limit=20
        )
        assert len(orders) == 1
        assert orders[0].purchaser_profile_id == mine
