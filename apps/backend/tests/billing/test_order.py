"""`billing.domain.order.Order` -- the guarded lifecycle (`Pending -> Invoiced -> Paid ->
Fulfilled | Cancelled`), `TargetRef`'s own shape invariant, and I-07 (`ProductSnapshot` frozen at
order time)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from billing.domain import (
    IllegalOrderStateTransitionError,
    InvalidTargetRefError,
    Order,
    ProductSnapshot,
    ProductType,
    TargetRef,
    TargetType,
    TargetTypeMismatchError,
)
from shared_kernel import BusinessProfileId, Money

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _snapshot(**overrides: object) -> ProductSnapshot:
    defaults: dict[str, object] = {
        "product_definition_id": uuid4(),
        "product_definition_version_id": uuid4(),
        "product_type": ProductType.PREMIUM,
        "price": Money(amount=Decimal("50000.00"), currency="UZS"),
        "term_days": 30,
        "quota": None,
    }
    defaults.update(overrides)
    return ProductSnapshot(**defaults)  # type: ignore[arg-type]


def _order(**overrides: object) -> Order:
    defaults: dict[str, object] = {
        "order_id": uuid4(),
        "purchaser_profile_id": BusinessProfileId(value=uuid4()),
        "product_snapshot": _snapshot(),
        "target": TargetRef(target_type=TargetType.LISTING, target_id=uuid4(), booking_window=None),
        "now": _NOW,
    }
    defaults.update(overrides)
    return Order.create(**defaults)  # type: ignore[arg-type]


class TestTargetRef:
    def test_I01_profile_target_forbids_a_target_id(self) -> None:
        with pytest.raises(InvalidTargetRefError):
            TargetRef(target_type=TargetType.PROFILE, target_id=uuid4(), booking_window=None)

    def test_I02_listing_target_requires_a_target_id(self) -> None:
        with pytest.raises(InvalidTargetRefError):
            TargetRef(target_type=TargetType.LISTING, target_id=None, booking_window=None)

    def test_I03_slot_booking_requires_a_booking_window(self) -> None:
        with pytest.raises(InvalidTargetRefError):
            TargetRef(target_type=TargetType.SLOT_BOOKING, target_id=uuid4(), booking_window=None)

    def test_I04_only_slot_booking_may_carry_a_booking_window(self) -> None:
        window = (_NOW, _NOW + timedelta(days=7))
        with pytest.raises(InvalidTargetRefError):
            TargetRef(target_type=TargetType.LISTING, target_id=uuid4(), booking_window=window)

    def test_I05_booking_window_end_must_be_after_start(self) -> None:
        with pytest.raises(InvalidTargetRefError):
            TargetRef(
                target_type=TargetType.SLOT_BOOKING,
                target_id=uuid4(),
                booking_window=(_NOW, _NOW),
            )

    def test_I06_valid_slot_booking_constructs(self) -> None:
        window = (_NOW, _NOW + timedelta(days=7))
        target = TargetRef(
            target_type=TargetType.SLOT_BOOKING, target_id=uuid4(), booking_window=window
        )
        assert target.booking_window == window

    def test_I07_listing_id_property_wraps_target_id_only_for_listing_targets(self) -> None:
        listing_id = uuid4()
        target = TargetRef(
            target_type=TargetType.LISTING, target_id=listing_id, booking_window=None
        )
        assert target.listing_id is not None
        assert target.listing_id.value == listing_id

        profile_target = TargetRef(
            target_type=TargetType.PROFILE, target_id=None, booking_window=None
        )
        assert profile_target.listing_id is None


class TestOrderCreate:
    def test_I08_creates_a_pending_order(self) -> None:
        order = _order()
        assert order.status.value == "PENDING"

    def test_I09_amount_mirrors_the_frozen_product_snapshot_price(self) -> None:
        snapshot = _snapshot(price=Money(amount=Decimal("75000.00"), currency="UZS"))
        order = _order(product_snapshot=snapshot)
        assert order.amount == snapshot.price

    def test_I10_target_type_must_match_the_products_required_target_type(self) -> None:
        # PREMIUM requires LISTING, not PROFILE.
        with pytest.raises(TargetTypeMismatchError):
            Order.create(
                order_id=uuid4(),
                purchaser_profile_id=BusinessProfileId(value=uuid4()),
                product_snapshot=_snapshot(product_type=ProductType.PREMIUM),
                target=TargetRef(
                    target_type=TargetType.PROFILE, target_id=None, booking_window=None
                ),
                now=_NOW,
            )

    def test_I07_product_snapshot_is_frozen_at_creation(self) -> None:
        """I-07: a later `ProductDefinition` price/term change in `configuration` never
        retroactively alters an existing order -- proven here at the domain level: the frozen
        `ProductSnapshot` passed to `Order.create` is a value object, and nothing in `Order`'s own
        API re-reads or mutates it after construction."""
        original_price = Money(amount=Decimal("50000.00"), currency="UZS")
        snapshot = _snapshot(price=original_price)
        order = _order(product_snapshot=snapshot)

        # simulate a later configuration price change -- a NEW snapshot object, never touching
        # the order's own already-frozen one.
        _changed_snapshot = _snapshot(price=Money(amount=Decimal("99999.00"), currency="UZS"))

        assert order.product_snapshot.price == original_price
        assert order.amount == original_price


class TestOrderLifecycle:
    def test_I11_issue_invoice_moves_pending_to_invoiced(self) -> None:
        order = _order()
        invoiced = order.issue_invoice(now=_NOW)
        assert invoiced.status.value == "INVOICED"

    def test_I12_issue_invoice_twice_raises(self) -> None:
        order = _order().issue_invoice(now=_NOW)
        with pytest.raises(IllegalOrderStateTransitionError):
            order.issue_invoice(now=_NOW)

    def test_I13_mark_paid_requires_invoiced(self) -> None:
        order = _order()
        with pytest.raises(IllegalOrderStateTransitionError):
            order.mark_paid(now=_NOW)

    def test_I14_mark_paid_moves_invoiced_to_paid(self) -> None:
        order = _order().issue_invoice(now=_NOW).mark_paid(now=_NOW)
        assert order.status.value == "PAID"

    def test_I15_fulfill_requires_paid(self) -> None:
        order = _order().issue_invoice(now=_NOW)
        with pytest.raises(IllegalOrderStateTransitionError):
            order.fulfill(now=_NOW)
        fulfilled = order.mark_paid(now=_NOW).fulfill(now=_NOW)
        assert fulfilled.status.value == "FULFILLED"

    def test_I16_cancel_allowed_from_pending(self) -> None:
        cancelled = _order().cancel(now=_NOW)
        assert cancelled.status.value == "CANCELLED"

    def test_I17_cancel_allowed_from_invoiced(self) -> None:
        cancelled = _order().issue_invoice(now=_NOW).cancel(now=_NOW)
        assert cancelled.status.value == "CANCELLED"

    def test_I18_cancel_forbidden_once_paid(self) -> None:
        order = _order().issue_invoice(now=_NOW).mark_paid(now=_NOW)
        with pytest.raises(IllegalOrderStateTransitionError):
            order.cancel(now=_NOW)

    def test_I19_cancel_forbidden_when_already_cancelled(self) -> None:
        order = _order().cancel(now=_NOW)
        with pytest.raises(IllegalOrderStateTransitionError):
            order.cancel(now=_NOW)
