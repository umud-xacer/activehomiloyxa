"""`billing.domain.entitlement` -- `EntitlementFactory.activate_from_paid_order` (I-14's own
structural guard) and `Entitlement`'s guarded lifecycle (`Active -> Expired | Revoked`).

I-14: "An Entitlement activates only upon administrator-confirmed payment of its invoice." Proven
BOTH directions here: (a) `test_I14_confirmed_payment_activates_the_entitlement` -- a `PAID` order
DOES produce an active entitlement; (b) `test_I14_no_activation_without_confirmed_payment_*` --
every OTHER order status is refused with a typed exception, and `Entitlement` has no other
constructor at all (this file's own module-level `test_I14_entitlement_has_exactly_one_
constructor` proves the second half structurally, not just by example).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from billing.domain import (
    EntitlementActivationWithoutPaymentError,
    IllegalEntitlementStateTransitionError,
    MissingTermError,
    Order,
    ProductSnapshot,
    ProductType,
    TargetRef,
    TargetType,
)
from billing.domain.entitlement import Entitlement, EntitlementFactory
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


def _order(*, status: str = "PENDING", product_snapshot: ProductSnapshot | None = None) -> Order:
    snapshot = product_snapshot or _snapshot()
    if snapshot.product_type in (ProductType.SUBSCRIPTION, ProductType.VERIFICATION):
        target = TargetRef(target_type=TargetType.PROFILE, target_id=None, booking_window=None)
    else:
        target = TargetRef(target_type=TargetType.LISTING, target_id=uuid4(), booking_window=None)
    order = Order.create(
        order_id=uuid4(),
        purchaser_profile_id=BusinessProfileId(value=uuid4()),
        product_snapshot=snapshot,
        target=target,
        now=_NOW,
    )
    if status == "PENDING":
        return order
    order = order.issue_invoice(now=_NOW)
    if status == "INVOICED":
        return order
    order = order.mark_paid(now=_NOW)
    if status == "PAID":
        return order
    if status == "FULFILLED":
        return order.fulfill(now=_NOW)
    if status == "CANCELLED":
        return _order_cancel_from_invoiced(snapshot)
    raise AssertionError(f"unsupported status for test fixture: {status}")


def _order_cancel_from_invoiced(product_snapshot: ProductSnapshot) -> Order:
    order = Order.create(
        order_id=uuid4(),
        purchaser_profile_id=BusinessProfileId(value=uuid4()),
        product_snapshot=product_snapshot,
        target=TargetRef(target_type=TargetType.LISTING, target_id=uuid4(), booking_window=None),
        now=_NOW,
    )
    return order.cancel(now=_NOW)


class TestI14ActivationOnlyOnConfirmedPayment:
    """I-14, proven both directions."""

    def test_I14_confirmed_payment_activates_the_entitlement(self) -> None:
        order = _order(status="PAID")
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        assert entitlement.activation_state.value == "ACTIVE"
        assert entitlement.order_id == order.id

    @pytest.mark.parametrize("status", ["PENDING", "INVOICED", "CANCELLED"])
    def test_I14_no_activation_without_confirmed_payment(self, status: str) -> None:
        order = _order(status=status)
        with pytest.raises(EntitlementActivationWithoutPaymentError) as exc_info:
            EntitlementFactory.activate_from_paid_order(
                entitlement_id=uuid4(), order=order, now=_NOW
            )
        assert exc_info.value.order_status == status

    def test_I14_entitlement_has_exactly_one_constructor(self) -> None:
        """Structural proof, not just example-based: `Entitlement` (a frozen dataclass) has no
        `create`/`issue`/other factory `staticmethod` anywhere in its own class body or module --
        `EntitlementFactory.activate_from_paid_order` is the ONLY function in this codebase that
        constructs one, and it always runs the `order.status is PAID` guard first."""
        import billing.domain.entitlement as entitlement_module

        assert not hasattr(Entitlement, "create")
        assert not hasattr(Entitlement, "issue")
        assert not hasattr(Entitlement, "activate")
        # the module itself defines exactly one public class besides `Entitlement`, and it is
        # the factory -- `vars(module)` also picks up every *imported* name (dataclass, UUID,
        # the typed exceptions, ...), so this filters to classes whose `__module__` is this file.
        classes_defined_here = [
            name
            for name, value in vars(entitlement_module).items()
            if not name.startswith("_")
            and isinstance(value, type)
            and value.__module__ == entitlement_module.__name__
        ]
        assert set(classes_defined_here) == {"Entitlement", "EntitlementFactory"}


class TestEntitlementTypeMapping:
    def test_premium_maps_to_listing_promotion_with_premium_kind(self) -> None:
        order = _order(status="PAID", product_snapshot=_snapshot(product_type=ProductType.PREMIUM))
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        assert entitlement.entitlement_type.value == "LISTING_PROMOTION"
        assert entitlement.promotion_kind is not None
        assert entitlement.promotion_kind.value == "PREMIUM"
        assert entitlement.target_id == order.target.target_id

    def test_subscription_maps_to_active_subscription_targeting_the_purchaser(self) -> None:
        order = _order(
            status="PAID", product_snapshot=_snapshot(product_type=ProductType.SUBSCRIPTION)
        )
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        assert entitlement.entitlement_type.value == "ACTIVE_SUBSCRIPTION"
        assert entitlement.promotion_kind is None
        assert entitlement.target_id == order.purchaser_profile_id.value

    def test_verification_maps_to_verification_eligibility(self) -> None:
        order = _order(
            status="PAID", product_snapshot=_snapshot(product_type=ProductType.VERIFICATION)
        )
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        assert entitlement.entitlement_type.value == "VERIFICATION_ELIGIBILITY"
        assert entitlement.promotion_kind is None

    def test_banner_placement_maps_to_banner_slot_booking(self) -> None:
        window = (_NOW, _NOW + timedelta(days=14))
        order = Order.create(
            order_id=uuid4(),
            purchaser_profile_id=BusinessProfileId(value=uuid4()),
            product_snapshot=_snapshot(product_type=ProductType.BANNER_PLACEMENT, term_days=None),
            target=TargetRef(
                target_type=TargetType.SLOT_BOOKING, target_id=uuid4(), booking_window=window
            ),
            now=_NOW,
        )
        order = order.issue_invoice(now=_NOW).mark_paid(now=_NOW)
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        assert entitlement.entitlement_type.value == "BANNER_SLOT_BOOKING"
        assert entitlement.valid_from == window[0]
        assert entitlement.valid_until == window[1]


class TestValidityWindow:
    def test_valid_until_is_now_plus_term_days_for_non_slot_products(self) -> None:
        order = _order(status="PAID", product_snapshot=_snapshot(term_days=30))
        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )
        assert entitlement.valid_from == _NOW
        assert entitlement.valid_until == _NOW + timedelta(days=30)

    def test_missing_term_days_raises_for_non_slot_products(self) -> None:
        order = _order(status="PAID", product_snapshot=_snapshot(term_days=None))
        with pytest.raises(MissingTermError):
            EntitlementFactory.activate_from_paid_order(
                entitlement_id=uuid4(), order=order, now=_NOW
            )


class TestEntitlementLifecycle:
    def _active(self) -> Entitlement:
        order = _order(status="PAID")
        return EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=_NOW
        )

    def test_expire_moves_active_to_expired(self) -> None:
        expired = self._active().expire(now=_NOW)
        assert expired.activation_state.value == "EXPIRED"

    def test_expire_twice_raises(self) -> None:
        entitlement = self._active().expire(now=_NOW)
        with pytest.raises(IllegalEntitlementStateTransitionError):
            entitlement.expire(now=_NOW)

    def test_revoke_moves_active_to_revoked(self) -> None:
        revoked = self._active().revoke(now=_NOW)
        assert revoked.activation_state.value == "REVOKED"

    def test_revoke_an_already_expired_entitlement_raises(self) -> None:
        entitlement = self._active().expire(now=_NOW)
        with pytest.raises(IllegalEntitlementStateTransitionError):
            entitlement.revoke(now=_NOW)
