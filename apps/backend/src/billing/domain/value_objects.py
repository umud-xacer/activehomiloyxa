"""billing -- value objects (DDD Sec 5.8 BC-08). Persistence-ignorant, mirrors
`catalog.domain.value_objects`'s style. `enum.StrEnum` (not `class X(str, Enum)`) for every new
closed vocabulary here -- `(str, Enum)` trips ruff's `UP042`; catalog's/identity's own
already-merged value objects use the older form (a pre-existing, out-of-scope violation, not
repeated here).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from billing.domain.exceptions import InvalidTargetRefError
from shared_kernel import ListingId, Money


class ProductType(StrEnum):
    """Verbatim from `contracts/openapi.yaml` `Product.productType` (BR-BILL-01, widened to eight
    closed monetisation-product types 2026-08-23 for the listing paywall: `LISTING_PUBLICATION`
    (pay once to publish a single held listing, target = the listing itself) and
    `LISTING_CREDIT_PACK` (bulk Start/Biznes/Unlim listing-credit packages, target = the
    purchaser) -- see `product_mapping.py`."""

    SUBSCRIPTION = "SUBSCRIPTION"
    PREMIUM = "PREMIUM"
    FEATURED = "FEATURED"
    TOP_PLACEMENT = "TOP_PLACEMENT"
    VERIFICATION = "VERIFICATION"
    BANNER_PLACEMENT = "BANNER_PLACEMENT"
    LISTING_PUBLICATION = "LISTING_PUBLICATION"
    LISTING_CREDIT_PACK = "LISTING_CREDIT_PACK"


class TargetType(StrEnum):
    """Verbatim from `contracts/openapi.yaml` `Order.targetType` / Physical DB Design's
    `ck_booking_shape` CHECK vocabulary."""

    PROFILE = "PROFILE"
    LISTING = "LISTING"
    SLOT_BOOKING = "SLOT_BOOKING"


class OrderStatus(StrEnum):
    """Verbatim from `contracts/openapi.yaml` `Order.status`. Fixed lifecycle: `PENDING ->
    INVOICED -> PAID -> FULFILLED | CANCELLED` (Domain Model Sec 5.8)."""

    PENDING = "PENDING"
    INVOICED = "INVOICED"
    PAID = "PAID"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class InvoiceStatus(StrEnum):
    """Verbatim from `contracts/openapi.yaml` `Invoice.status`. Fixed lifecycle: `ISSUED -> PAID
    | VOID` (Domain Model Sec 5.8; Physical DB `ck_paid_shape`)."""

    ISSUED = "ISSUED"
    PAID = "PAID"
    VOID = "VOID"


class EntitlementType(StrEnum):
    """Verbatim from `contracts/openapi.yaml` `Entitlement.entitlementType` (Domain Model Sec 5.8,
    widened to six closed entitlement types 2026-08-23 for the listing paywall:
    `LISTING_PUBLICATION` (one-time grant that flips one specific held listing live) and
    `LISTING_CREDIT_BALANCE` (a standing, decrementable balance of future publish credits) --
    see `product_mapping.py`."""

    ACTIVE_SUBSCRIPTION = "ACTIVE_SUBSCRIPTION"
    LISTING_PROMOTION = "LISTING_PROMOTION"
    VERIFICATION_ELIGIBILITY = "VERIFICATION_ELIGIBILITY"
    BANNER_SLOT_BOOKING = "BANNER_SLOT_BOOKING"
    LISTING_PUBLICATION = "LISTING_PUBLICATION"
    LISTING_CREDIT_BALANCE = "LISTING_CREDIT_BALANCE"


class PromotionKind(StrEnum):
    """Verbatim from `contracts/openapi.yaml` `Entitlement.promotionKind` -- set only when
    `entitlement_type == LISTING_PROMOTION` (Physical DB `ck_promo_shape`). Deliberately
    duplicated here rather than imported from `search.domain.value_objects.PromotionKind`:
    billing must not import search (`billing-scope`), and a value's *shape* crossing an event
    payload is not the same thing as depending on the consuming module's code -- the same
    reasoning `search.domain.value_objects` itself already documents for its own re-declaration
    of catalog's `ListingType`/`PromotionKind`."""

    PREMIUM = "PREMIUM"
    FEATURED = "FEATURED"
    TOP_PLACEMENT = "TOP_PLACEMENT"


class ActivationState(StrEnum):
    """Verbatim from `contracts/openapi.yaml` `Entitlement.activationState`. Fixed lifecycle:
    `ACTIVE -> EXPIRED | REVOKED` (Domain Model Sec 5.8), both terminal."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


@dataclass(frozen=True)
class ProductSnapshot:
    """The frozen product data captured into an `Order` at order time (I-07's "frozen snapshot"
    pattern, applied here per DB Architecture Sec 1.2: "ProductSnapshot inside Order"). A later
    `ProductDefinition` price/term change in `configuration` never retroactively alters an
    existing order -- this is exactly why every field the order needs is copied here rather than
    referenced live."""

    product_definition_id: UUID
    product_definition_version_id: UUID
    product_type: ProductType
    price: Money
    term_days: int | None
    """`None` only for `BANNER_PLACEMENT` products, whose validity window comes from the order's
    own `TargetRef.booking_window` instead of a fixed term."""
    quota: dict[str, object] | None
    """`SUBSCRIPTION` only -- BRULE-07 listing quotas/limits, carried verbatim into
    `EntitlementActivated`'s payload for catalog's own quota projection."""


@dataclass(frozen=True)
class TargetRef:
    """What a purchased product applies to (Domain Model Sec 5.8). Physical DB's
    `ck_booking_shape` CHECK, realised here as a construction-time invariant rather than trusted
    to the caller: `target_id` is required for `LISTING`/`SLOT_BOOKING` and forbidden for
    `PROFILE`; `booking_window` is required for, and only for, `SLOT_BOOKING`."""

    target_type: TargetType
    target_id: UUID | None
    booking_window: tuple[datetime, datetime] | None

    def __post_init__(self) -> None:
        if self.target_type is TargetType.PROFILE and self.target_id is not None:
            raise InvalidTargetRefError("PROFILE targets must not carry a target_id")
        if (
            self.target_type in (TargetType.LISTING, TargetType.SLOT_BOOKING)
            and self.target_id is None
        ):
            raise InvalidTargetRefError(f"{self.target_type.value} targets require a target_id")
        booking_window = self.booking_window
        if (self.target_type is TargetType.SLOT_BOOKING) != (booking_window is not None):
            raise InvalidTargetRefError(
                "booking_window is required for, and only for, SLOT_BOOKING targets"
            )
        if booking_window is not None:
            start, end = booking_window
            if end <= start:
                raise InvalidTargetRefError("booking_window end must be strictly after start")

    @property
    def listing_id(self) -> ListingId | None:
        """Convenience accessor for `LISTING`-targeted orders -- never imports `catalog.domain`,
        just wraps the raw `target_id` in the shared-kernel typed id."""
        if self.target_type is not TargetType.LISTING or self.target_id is None:
            return None
        return ListingId(value=self.target_id)


@dataclass(frozen=True)
class PaymentConfirmation:
    """FR-BILL-002's own acceptance criterion fields, captured on `Invoice.confirm_payment`."""

    confirmed_by: UUID
    """Operator account id (`identity` acting-user, carried as a bare `UUID` -- billing never
    imports identity.domain, matching catalog's own composition-root-only bridging discipline)."""
    confirmed_at: datetime
    note: str | None
