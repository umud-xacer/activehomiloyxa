"""billing -- typed domain exceptions, one per invariant violated (Playbook Sec 6). Mirrors
`catalog.domain.exceptions`'s style. `interfaces/errors.py` maps each of these to a
`contracts.errors.Problem` (closed `ErrorCode` vocabulary).
"""

from __future__ import annotations

from uuid import UUID


class BillingDomainError(Exception):
    """Base for every typed exception raised by billing's domain/ layer."""


# --- Order lifecycle (OrderStatus: Pending -> Invoiced -> Paid -> Fulfilled | Cancelled) --------


class IllegalOrderStateTransitionError(BillingDomainError):
    """Attempted a transition method from an `OrderStatus` it does not accept."""

    def __init__(self, transition: str, current: str) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} an order in status {current}")


class InvalidTargetRefError(BillingDomainError):
    """`TargetRef`'s own shape invariant (Physical DB `ck_booking_shape`): `target_id` is
    required for `LISTING`/`SLOT_BOOKING` targets and forbidden for `PROFILE`; `booking_window`
    is required for, and only for, `SLOT_BOOKING`."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"invalid TargetRef: {reason}")


class TargetTypeMismatchError(BillingDomainError):
    """`Order.create`'s own construction invariant: a product's `ProductType` fixes which
    `TargetType` it requires (`billing.domain.product_mapping.REQUIRED_TARGET_TYPE_BY_PRODUCT`)
    -- e.g. a `PREMIUM` promotion always targets a listing, never a profile. Enforced once, at
    order creation, so `EntitlementFactory` never has to re-validate the pairing against an
    already-PAID order."""

    def __init__(self, product_type: str, required: str, actual: str) -> None:
        self.product_type = product_type
        self.required = required
        self.actual = actual
        super().__init__(
            f"product type {product_type!r} requires target type {required!r}, got {actual!r}"
        )


# --- Invoice lifecycle (InvoiceStatus: Issued -> Paid | Void) -----------------------------------


class IllegalInvoiceStateTransitionError(BillingDomainError):
    """Attempted a transition method from an `InvoiceStatus` it does not accept."""

    def __init__(self, transition: str, current: str) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} an invoice in status {current}")


# --- Entitlement activation (I-14, BRULE-14) -----------------------------------------------------


class EntitlementActivationWithoutPaymentError(BillingDomainError):
    """I-14: "An Entitlement activates only upon administrator-confirmed payment of its invoice."
    Raised by `EntitlementFactory.activate_from_paid_order` if given an order that is not, in
    fact, `PAID` -- the one guard that makes "no code path activates an entitlement without a
    confirmed payment" true structurally, not just by caller discipline."""

    def __init__(self, order_id: UUID, order_status: str) -> None:
        self.order_id = order_id
        self.order_status = order_status
        super().__init__(
            f"cannot activate an entitlement for order {order_id}: order status is "
            f"{order_status!r}, not PAID"
        )


class IllegalEntitlementStateTransitionError(BillingDomainError):
    """Attempted a transition method from an `ActivationState` it does not accept
    (`ACTIVE -> EXPIRED | REVOKED`; both terminal)."""

    def __init__(self, transition: str, current: str) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} an entitlement in activation state {current}")


class UnsupportedProductTypeError(BillingDomainError):
    """`EntitlementFactory`'s ProductType -> EntitlementType mapping is a fixed [P] six-case
    switch (Domain Model Sec 5.8's four-member `EntitlementType` closed set, `Product.
    productType`'s six-member closed set) -- reaching this means a `ProductSnapshot` carries a
    `product_type` value outside that fixed vocabulary, which can only happen if `configuration`'s
    own whitelist is ever widened without a corresponding update here (fails closed rather than
    guessing a mapping)."""

    def __init__(self, product_type: str) -> None:
        self.product_type = product_type
        super().__init__(f"no EntitlementType mapping is defined for product type {product_type!r}")


class MissingTermError(BillingDomainError):
    """A non-`SLOT_BOOKING` product's `ProductSnapshot.term_days` is `None` -- every entitlement
    type except `BANNER_SLOT_BOOKING` (which derives its validity window from the order's own
    `booking_window` instead) needs a term to compute `valid_until` from. Fails closed (Playbook
    Sec 6) rather than inventing a default term configuration never specified."""

    def __init__(self, product_type: str) -> None:
        self.product_type = product_type
        super().__init__(
            f"product type {product_type!r} has no term_days configured; cannot compute "
            "entitlement validity"
        )


class NoCreditsRemainingError(BillingDomainError):
    """Listing paywall Phase 4 (2026-08-23): `Entitlement.consume_credit` on a
    `LISTING_CREDIT_BALANCE` entitlement whose `remaining_credits` is already `0`. Callers
    (`EntitlementUseCases.consume_listing_credit`) are expected to filter these out before
    calling -- reaching this means a caller consumed the same entitlement twice without
    re-reading it, a programming error, not a normal "no credits" business outcome (that case is
    `consume_listing_credit` returning `None`, never this exception)."""

    def __init__(self, entitlement_id: UUID) -> None:
        self.entitlement_id = entitlement_id
        super().__init__(f"entitlement {entitlement_id} has no remaining_credits left to consume")
