"""billing -- the `Entitlement` aggregate (DDD Sec 5.8 `AR: Entitlement [P]`) and
`EntitlementFactory` (I-14's own structural guard). Every `Entitlement` row's `valid_from`/
`valid_until` are `NOT NULL` at the physical layer (Physical DB Design's own column table) --
matching that exactly, this module has no "pending" or "inactive" entitlement representation:
an `Entitlement` simply does not exist until `EntitlementFactory.activate_from_paid_order`
constructs one, and that one method is the ONLY place an `Entitlement` is ever constructed.
This is what makes I-14 ("an Entitlement activates only upon administrator-confirmed payment of
its invoice") true structurally rather than by caller discipline: there is no other constructor,
no default, no "create then activate later" two-step path to bypass.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from billing.domain.exceptions import (
    EntitlementActivationWithoutPaymentError,
    IllegalEntitlementStateTransitionError,
    InvalidTargetRefError,
    MissingTermError,
    NoCreditsRemainingError,
    UnsupportedProductTypeError,
)
from billing.domain.order import Order
from billing.domain.product_mapping import (
    ENTITLEMENT_TYPE_BY_PRODUCT,
    PROMOTION_KIND_BY_PRODUCT,
)
from billing.domain.value_objects import (
    ActivationState,
    EntitlementType,
    ProductType,
    PromotionKind,
)


@dataclass(frozen=True)
class Entitlement:
    id: UUID
    order_id: UUID
    entitlement_type: EntitlementType
    promotion_kind: PromotionKind | None
    """Set if, and only if, `entitlement_type is LISTING_PROMOTION` (Physical DB `ck_promo_shape`
    -- enforced by `EntitlementFactory`, the only constructor, never by a runtime check here)."""
    target_id: UUID
    """The benefit target: the purchaser's own profile for `ACTIVE_SUBSCRIPTION`/
    `VERIFICATION_ELIGIBILITY`, the listing id for `LISTING_PROMOTION`, the slot booking's target
    id for `BANNER_SLOT_BOOKING`."""
    valid_from: datetime
    valid_until: datetime
    activation_state: ActivationState
    created_at: datetime
    updated_at: datetime
    remaining_credits: int | None = None
    """`LISTING_CREDIT_BALANCE` only (listing paywall Phase 4, 2026-08-23): the number of
    listing-publish credits left on this pack, decremented by `consume_credit`. `None` means
    unlimited (the Unlim/Premium tier's `unlimited_listing_publish` quota flag) -- never
    decremented, never exhausted. Every other `EntitlementType` leaves this `None` too, but for
    them it carries no meaning at all (there is nothing to consume)."""
    lock_version: int = 0

    def consume_credit(self, *, now: datetime) -> Entitlement:
        """Decrements `remaining_credits` by one. A no-op replace (still bumps `updated_at`) for
        an unlimited pack (`remaining_credits is None`) -- there is nothing to decrement. Raises
        if this entitlement isn't `ACTIVE`, or is already at zero (`NoCreditsRemainingError` --
        `EntitlementUseCases.consume_listing_credit`'s own selection query is expected to filter
        exhausted entitlements out before ever calling this; reaching either guard here is a
        caller bug, not a normal "no credits" outcome)."""
        if self.activation_state is not ActivationState.ACTIVE:
            raise IllegalEntitlementStateTransitionError(
                "consume_credit", self.activation_state.value
            )
        if self.remaining_credits is None:
            return replace(self, updated_at=now)
        if self.remaining_credits <= 0:
            raise NoCreditsRemainingError(self.id)
        return replace(self, remaining_credits=self.remaining_credits - 1, updated_at=now)

    def expire(self, *, now: datetime) -> Entitlement:
        """FR-SUBS-004/I-15: "the system SHALL deactivate entitlements at end of term" -- "an
        expired Entitlement confers no benefit ... withdrawn on `EntitlementExpired`." `ACTIVE ->
        EXPIRED` only; called by `infrastructure.worker.EntitlementExpiryWorker`'s sweep, never
        by a request-path use case."""
        if self.activation_state is not ActivationState.ACTIVE:
            raise IllegalEntitlementStateTransitionError("expire", self.activation_state.value)
        return replace(self, activation_state=ActivationState.EXPIRED, updated_at=now)

    def revoke(self, *, now: datetime) -> Entitlement:
        """Administrative early withdrawal (e.g. a chargeback or moderation action) -- `ACTIVE ->
        REVOKED` only. No OpenAPI operation exposes this in v1; provided for lifecycle
        completeness matching the documented `ActivationState` state machine (`Active -> Expired |
        Revoked`), the same "capability exists, no caller wires it yet" note as `Order.fulfill`/
        `Invoice.void`."""
        if self.activation_state is not ActivationState.ACTIVE:
            raise IllegalEntitlementStateTransitionError("revoke", self.activation_state.value)
        return replace(self, activation_state=ActivationState.REVOKED, updated_at=now)


class EntitlementFactory:
    """DDD Sec 5.8 `Factories | EntitlementFactory — creates the correct entitlement kind from a
    paid order's ProductSnapshot (FR-SUBS-003, BRULE-14)`. Stateless: every input it needs
    (the `Order`, already `PAID`) is passed in; it performs no I/O of its own."""

    @staticmethod
    def activate_from_paid_order(
        *, entitlement_id: UUID, order: Order, now: datetime
    ) -> Entitlement:
        """I-14's own structural guard: raises `EntitlementActivationWithoutPaymentError` unless
        `order.status is PAID` -- this is the one check that makes "no code path activates an
        entitlement without a confirmed payment" true regardless of what calls this method."""
        if order.status.value != "PAID":
            raise EntitlementActivationWithoutPaymentError(order.id, order.status.value)

        product_type = order.product_snapshot.product_type
        entitlement_type = ENTITLEMENT_TYPE_BY_PRODUCT.get(product_type)
        if entitlement_type is None:
            raise UnsupportedProductTypeError(product_type.value)
        promotion_kind = PROMOTION_KIND_BY_PRODUCT.get(product_type)

        target_id = (
            order.target.target_id
            if order.target.target_id is not None
            else order.purchaser_profile_id.value
        )

        valid_from, valid_until = _validity_window(order=order, product_type=product_type, now=now)

        return Entitlement(
            id=entitlement_id,
            order_id=order.id,
            entitlement_type=entitlement_type,
            promotion_kind=promotion_kind,
            target_id=target_id,
            valid_from=valid_from,
            valid_until=valid_until,
            activation_state=ActivationState.ACTIVE,
            created_at=now,
            updated_at=now,
            remaining_credits=_initial_remaining_credits(
                entitlement_type=entitlement_type, quota=order.product_snapshot.quota
            ),
        )


def _initial_remaining_credits(
    *, entitlement_type: EntitlementType, quota: dict[str, object] | None
) -> int | None:
    """Listing paywall Phase 4 (2026-08-23). Only `LISTING_CREDIT_BALANCE` ever carries a
    starting balance; every other entitlement type leaves this `None` (meaningless for them, not
    "unlimited"). `quota["unlimited_listing_publish"]` (the Unlim/Premium tier,
    `configuration.domain.content.QuotaSetContent`) takes precedence and yields `None` (unlimited,
    never decremented) even if `listing_publish_credits` also happens to be set."""
    if entitlement_type is not EntitlementType.LISTING_CREDIT_BALANCE:
        return None
    quota = quota or {}
    if quota.get("unlimited_listing_publish"):
        return None
    credits_raw = quota.get("listing_publish_credits")
    return int(credits_raw) if isinstance(credits_raw, int) else None


def _validity_window(
    *, order: Order, product_type: ProductType, now: datetime
) -> tuple[datetime, datetime]:
    if product_type is ProductType.BANNER_PLACEMENT:
        # `Order.create`'s own `TargetTypeMismatchError` guard already proved
        # `order.target.target_type is SLOT_BOOKING` for this product type, and `TargetRef`'s own
        # construction invariant already proved `booking_window` is present whenever
        # `target_type is SLOT_BOOKING` -- both checked once, at order creation. Re-checked here
        # (not asserted, QG-07/Security Architecture I-5: asserts must never gate production
        # control flow) rather than trusted blindly.
        if order.target.booking_window is None:
            raise InvalidTargetRefError(
                "BANNER_PLACEMENT entitlement activation requires an order target with a "
                "booking_window"
            )
        return order.target.booking_window
    term_days = order.product_snapshot.term_days
    if term_days is None:
        raise MissingTermError(product_type.value)
    valid_from = now
    valid_until = valid_from + timedelta(days=term_days)
    return valid_from, valid_until
