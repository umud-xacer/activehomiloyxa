"""`billing.application.entitlement_use_cases.EntitlementUseCases` -- `list_my_entitlements` and
the expiry sweep (FR-SUBS-004/I-15)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from billing.application.entitlement_use_cases import EntitlementUseCases
from billing.application.exceptions import EntitlementNotFoundError, OrderNotFoundError
from billing.domain import (
    EntitlementFactory,
    Order,
    ProductSnapshot,
    ProductType,
    TargetRef,
    TargetType,
)
from shared_kernel import BusinessProfileId, Money

from .conftest import FakeEntitlementRepository, FakeOrderRepository, FakeOutbox

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.fixture
def use_cases(
    fake_entitlements: FakeEntitlementRepository,
    fake_orders: FakeOrderRepository,
    fake_outbox: FakeOutbox,
) -> EntitlementUseCases:
    return EntitlementUseCases(
        entitlements=fake_entitlements, orders=fake_orders, outbox=fake_outbox
    )


def _paid_order(*, purchaser: BusinessProfileId | None = None) -> Order:
    snapshot = ProductSnapshot(
        product_definition_id=uuid4(),
        product_definition_version_id=uuid4(),
        product_type=ProductType.PREMIUM,
        price=Money(amount=Decimal("50000.00"), currency="UZS"),
        term_days=30,
        quota=None,
    )
    order = Order.create(
        order_id=uuid4(),
        purchaser_profile_id=purchaser or BusinessProfileId(value=uuid4()),
        product_snapshot=snapshot,
        target=TargetRef(target_type=TargetType.LISTING, target_id=uuid4(), booking_window=None),
        now=_NOW,
    )
    return order.issue_invoice(now=_NOW).mark_paid(now=_NOW)


class TestListMyEntitlements:
    async def test_returns_only_active_entitlements_by_default(
        self,
        use_cases: EntitlementUseCases,
        fake_entitlements: FakeEntitlementRepository,
        fake_orders: FakeOrderRepository,
    ) -> None:
        purchaser = BusinessProfileId(value=uuid4())
        order = _paid_order(purchaser=purchaser)
        await fake_orders.add(order)
        active = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        await fake_entitlements.add(active)
        # a second, expired entitlement for the same purchaser, a different listing target.
        other_order = _paid_order(purchaser=purchaser)
        await fake_orders.add(other_order)
        other = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=other_order, now=_NOW
        ).expire(now=_NOW + timedelta(days=31))
        await fake_entitlements.add(other)

        results = await use_cases.list_my_entitlements(
            purchaser_profile_id=purchaser, active_only=True
        )
        assert {e.id for e in results} == {active.id}

        all_results = await use_cases.list_my_entitlements(
            purchaser_profile_id=purchaser, active_only=False
        )
        assert {e.id for e in all_results} == {active.id, other.id}


class TestSweepExpired:
    async def test_expires_entitlements_past_their_valid_until(
        self,
        use_cases: EntitlementUseCases,
        fake_entitlements: FakeEntitlementRepository,
        fake_orders: FakeOrderRepository,
        fake_outbox: FakeOutbox,
    ) -> None:
        order = _paid_order()
        await fake_orders.add(order)
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        await fake_entitlements.add(entitlement)

        swept_at = _NOW + timedelta(days=31)
        swept_count = await use_cases.sweep_expired(now=swept_at, batch_size=50)

        assert swept_count == 1
        assert fake_entitlements.entitlements[entitlement.id].activation_state.value == "EXPIRED"
        assert [e.event_type for e in fake_outbox.events] == ["EntitlementExpired"]

    async def test_does_not_touch_entitlements_still_within_their_term(
        self,
        use_cases: EntitlementUseCases,
        fake_entitlements: FakeEntitlementRepository,
        fake_orders: FakeOrderRepository,
    ) -> None:
        order = _paid_order()
        await fake_orders.add(order)
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        await fake_entitlements.add(entitlement)

        swept_count = await use_cases.sweep_expired(now=_NOW + timedelta(days=1), batch_size=50)

        assert swept_count == 0
        assert fake_entitlements.entitlements[entitlement.id].activation_state.value == "ACTIVE"

    async def test_expiry_event_payload_carries_listing_id_for_search(
        self,
        use_cases: EntitlementUseCases,
        fake_entitlements: FakeEntitlementRepository,
        fake_orders: FakeOrderRepository,
        fake_outbox: FakeOutbox,
    ) -> None:
        order = _paid_order()
        await fake_orders.add(order)
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        await fake_entitlements.add(entitlement)

        await use_cases.sweep_expired(now=_NOW + timedelta(days=31), batch_size=50)

        payload = fake_outbox.events[0].payload
        assert payload["listingId"] == str(order.target.target_id)
        assert payload["kind"] == "PREMIUM"

    async def test_raises_order_not_found_when_the_entitlements_order_is_missing(
        self,
        use_cases: EntitlementUseCases,
        fake_entitlements: FakeEntitlementRepository,
        fake_orders: FakeOrderRepository,
    ) -> None:
        order = _paid_order()
        await fake_orders.add(order)
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        await fake_entitlements.add(entitlement)
        del fake_orders.orders[order.id]

        with pytest.raises(OrderNotFoundError):
            await use_cases.sweep_expired(now=_NOW + timedelta(days=31), batch_size=50)


class TestRevoke:
    async def test_revokes_an_active_entitlement_and_emits_the_event(
        self,
        use_cases: EntitlementUseCases,
        fake_entitlements: FakeEntitlementRepository,
        fake_orders: FakeOrderRepository,
        fake_outbox: FakeOutbox,
    ) -> None:
        order = _paid_order()
        await fake_orders.add(order)
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        await fake_entitlements.add(entitlement)

        revoked = await use_cases.revoke(entitlement.id, now=_NOW)

        assert revoked.activation_state.value == "REVOKED"
        assert fake_entitlements.entitlements[entitlement.id].activation_state.value == "REVOKED"
        assert [e.event_type for e in fake_outbox.events] == ["EntitlementRevoked"]
        payload = fake_outbox.events[0].payload
        assert payload["listingId"] == str(order.target.target_id)

    async def test_raises_entitlement_not_found_for_an_unknown_id(
        self, use_cases: EntitlementUseCases
    ) -> None:
        with pytest.raises(EntitlementNotFoundError):
            await use_cases.revoke(uuid4(), now=_NOW)

    async def test_raises_order_not_found_when_the_entitlements_order_is_missing(
        self,
        use_cases: EntitlementUseCases,
        fake_entitlements: FakeEntitlementRepository,
        fake_orders: FakeOrderRepository,
    ) -> None:
        order = _paid_order()
        await fake_orders.add(order)
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        await fake_entitlements.add(entitlement)
        del fake_orders.orders[order.id]

        with pytest.raises(OrderNotFoundError):
            await use_cases.revoke(entitlement.id, now=_NOW)
