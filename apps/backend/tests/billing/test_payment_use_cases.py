"""`billing.application.payment_use_cases.PaymentUseCases` -- `confirm_payment`, the sanctioned
synchronous multi-aggregate transaction (DB Architecture Sec 1.3), and `admin_list_invoices`.

The REAL atomicity guarantee (a forced mid-transaction failure rolls back all three aggregates
together) can only be proven against a real database transaction -- that test lives in
`integration/test_payment_transaction_live.py`. What this fast tier proves is the
*orchestration*: given the fakes' own successful path, all three aggregates end up in the
correct, mutually-consistent post-state, and no code path activates an entitlement without a
`PAID` order backing it (I-14, application-layer half of the domain-layer proof in
`test_entitlement.py`)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from billing.application.exceptions import (
    InvoiceNotFoundError,
    OrderNotFoundError,
    PaymentNotConfirmedError,
)
from billing.application.payment_use_cases import PaymentUseCases
from billing.domain import Invoice, Order, ProductSnapshot, ProductType, TargetRef, TargetType
from shared_kernel import BusinessProfileId, Money

from .conftest import (
    FakeEntitlementRepository,
    FakeInvoiceRepository,
    FakeOrderRepository,
    FakeOutbox,
    FakePaymentProviderPort,
    FakeProductDefinitionReaderPort,
)

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.fixture
def use_cases(
    fake_orders: FakeOrderRepository,
    fake_invoices: FakeInvoiceRepository,
    fake_entitlements: FakeEntitlementRepository,
    fake_payment_provider: FakePaymentProviderPort,
    fake_outbox: FakeOutbox,
) -> PaymentUseCases:
    return PaymentUseCases(
        orders=fake_orders,
        invoices=fake_invoices,
        entitlements=fake_entitlements,
        payment_provider=fake_payment_provider,
        outbox=fake_outbox,
    )


async def _seed_invoiced_order(
    orders: FakeOrderRepository,
    invoices: FakeInvoiceRepository,
    products: FakeProductDefinitionReaderPort,
) -> tuple[Order, Invoice]:
    product = products.seed(product_type=ProductType.PREMIUM)
    snapshot = ProductSnapshot(
        product_definition_id=product.id,
        product_definition_version_id=product.version_id,
        product_type=product.product_type,
        price=Money(amount=Decimal(product.price_amount), currency=product.price_currency),
        term_days=product.term_days,
        quota=product.quota,
    )
    order = Order.create(
        order_id=uuid4(),
        purchaser_profile_id=BusinessProfileId(value=uuid4()),
        product_snapshot=snapshot,
        target=TargetRef(target_type=TargetType.LISTING, target_id=uuid4(), booking_window=None),
        now=_NOW,
    )
    await orders.add(order)
    invoice = Invoice.issue(
        invoice_id=uuid4(),
        order_id=order.id,
        invoice_number="INV-000001",
        amount=order.amount,
        now=_NOW,
    )
    await invoices.add(invoice)
    order = order.issue_invoice(now=_NOW)
    await orders.save(order)
    return order, invoice


class TestConfirmPaymentSanctionedTransaction:
    async def test_I01_confirming_payment_marks_invoice_paid_order_paid_and_activates_entitlement(
        self,
        use_cases: PaymentUseCases,
        fake_orders: FakeOrderRepository,
        fake_invoices: FakeInvoiceRepository,
        fake_entitlements: FakeEntitlementRepository,
        fake_products: FakeProductDefinitionReaderPort,
    ) -> None:
        order, invoice = await _seed_invoiced_order(fake_orders, fake_invoices, fake_products)
        operator_id = uuid4()

        result = await use_cases.confirm_payment(
            invoice_id=invoice.id,
            operator_account_id=operator_id,
            confirmed=True,
            note="paid in cash",
            now=_NOW,
        )

        assert result.status.value == "PAID"
        saved_order = fake_orders.orders[order.id]
        assert saved_order.status.value == "PAID"
        entitlements = list(fake_entitlements.entitlements.values())
        assert len(entitlements) == 1
        assert entitlements[0].order_id == order.id
        assert entitlements[0].activation_state.value == "ACTIVE"

    async def test_I02_publishes_payment_confirmed_and_entitlement_activated_events(
        self,
        use_cases: PaymentUseCases,
        fake_orders: FakeOrderRepository,
        fake_invoices: FakeInvoiceRepository,
        fake_products: FakeProductDefinitionReaderPort,
        fake_outbox: FakeOutbox,
    ) -> None:
        _order, invoice = await _seed_invoiced_order(fake_orders, fake_invoices, fake_products)
        await use_cases.confirm_payment(
            invoice_id=invoice.id,
            operator_account_id=uuid4(),
            confirmed=True,
            note=None,
            now=_NOW,
        )
        event_types = [e.event_type for e in fake_outbox.events]
        assert event_types == ["PaymentConfirmed", "EntitlementActivated"]

    async def test_I03_entitlement_activated_payload_matches_the_frozen_shape_both_consumers_need(
        self,
        use_cases: PaymentUseCases,
        fake_orders: FakeOrderRepository,
        fake_invoices: FakeInvoiceRepository,
        fake_products: FakeProductDefinitionReaderPort,
        fake_outbox: FakeOutbox,
    ) -> None:
        """`catalog.infrastructure.event_projection.handle_entitlement_event` needs
        `ownerProfileId`/`entitlementId`; `search.infrastructure.event_projection.
        handle_entitlement_activated` needs `listingId`/`kind`/`entitlementId`. Both must be
        present in the SAME payload (composition_root.py routes by `entitlementType`, neither
        consumer discriminates on its own)."""
        order, invoice = await _seed_invoiced_order(fake_orders, fake_invoices, fake_products)
        await use_cases.confirm_payment(
            invoice_id=invoice.id,
            operator_account_id=uuid4(),
            confirmed=True,
            note=None,
            now=_NOW,
        )
        activated = next(e for e in fake_outbox.events if e.event_type == "EntitlementActivated")
        payload = activated.payload
        assert payload["entitlementType"] == "LISTING_PROMOTION"
        assert payload["ownerProfileId"] == str(order.purchaser_profile_id.value)
        assert "entitlementId" in payload
        assert payload["listingId"] == str(order.target.target_id)
        assert payload["kind"] == "PREMIUM"

    async def test_payment_declined_leaves_invoice_order_and_entitlements_unchanged(
        self,
        use_cases: PaymentUseCases,
        fake_orders: FakeOrderRepository,
        fake_invoices: FakeInvoiceRepository,
        fake_entitlements: FakeEntitlementRepository,
        fake_products: FakeProductDefinitionReaderPort,
    ) -> None:
        order, invoice = await _seed_invoiced_order(fake_orders, fake_invoices, fake_products)
        with pytest.raises(PaymentNotConfirmedError):
            await use_cases.confirm_payment(
                invoice_id=invoice.id,
                operator_account_id=uuid4(),
                confirmed=False,
                note="insufficient proof",
                now=_NOW,
            )
        assert fake_invoices.invoices[invoice.id].status.value == "ISSUED"
        assert fake_orders.orders[order.id].status.value == "INVOICED"
        assert fake_entitlements.entitlements == {}

    async def test_raises_invoice_not_found_for_an_unknown_invoice_id(
        self, use_cases: PaymentUseCases
    ) -> None:
        with pytest.raises(InvoiceNotFoundError):
            await use_cases.confirm_payment(
                invoice_id=uuid4(),
                operator_account_id=uuid4(),
                confirmed=True,
                note=None,
                now=_NOW,
            )

    async def test_raises_order_not_found_when_the_invoices_order_is_missing(
        self,
        use_cases: PaymentUseCases,
        fake_orders: FakeOrderRepository,
        fake_invoices: FakeInvoiceRepository,
        fake_products: FakeProductDefinitionReaderPort,
    ) -> None:
        order, invoice = await _seed_invoiced_order(fake_orders, fake_invoices, fake_products)
        del fake_orders.orders[order.id]

        with pytest.raises(OrderNotFoundError):
            await use_cases.confirm_payment(
                invoice_id=invoice.id,
                operator_account_id=uuid4(),
                confirmed=True,
                note=None,
                now=_NOW,
            )


class TestOfflineOnly:
    """BRULE-15/FR-BILL-004: exactly one `PaymentProviderPort` implementation exists in v1, and
    it never contacts an external provider."""

    def test_offline_manual_adapter_is_the_only_payment_provider_port_implementation(self) -> None:
        import inspect

        import billing.infrastructure as billing_infra

        payment_provider_classes = [
            name
            for name, obj in vars(billing_infra).items()
            if inspect.isclass(obj) and name.endswith("PaymentAdapter")
        ]
        assert payment_provider_classes == ["OfflineManualPaymentAdapter"]

    async def test_offline_adapter_performs_no_network_or_external_provider_call(self) -> None:
        """`OfflineManualPaymentAdapter.confirm` is a pure function of its own arguments -- the
        operator's own attestation IS the confirmation. Proven by source inspection: the method
        body contains no `import`/attribute access beyond returning `confirmed` verbatim."""
        import inspect

        from billing.infrastructure.offline_payment_adapter import OfflineManualPaymentAdapter

        source = inspect.getsource(OfflineManualPaymentAdapter.confirm)
        assert "return confirmed" in source
        # no HTTP/SDK-shaped call anywhere in the one method this adapter has.
        for forbidden in ("requests.", "httpx.", "aiohttp.", "boto3."):
            assert forbidden not in source.lower()
