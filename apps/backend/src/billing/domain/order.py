"""billing -- the `Order` aggregate (DDD Sec 5.8 `AR: Order [P]`). Persistence-ignorant, mirrors
`catalog.domain.listing.Listing`'s style exactly: frozen dataclass, every state transition
returns a new instance via `dataclasses.replace`, guarded by a typed exception raised before the
replace. `Order.mark_paid()` is the "Order.confirmPayment() style" method the Database
Architecture document names as the pattern to follow (Sec 18 "AI Development Guidance": "state
transitions happen inside domain objects ... guarded by the invariant").

`ProductSnapshot` is frozen into the order at `create()` time and never re-read from
`configuration` again (I-07's frozen-snapshot pattern) -- a later `ProductDefinition` price/term
change never retroactively alters an existing order, proven by
`test_order.py::test_I07_product_snapshot_is_frozen_at_creation`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from billing.domain.exceptions import IllegalOrderStateTransitionError, TargetTypeMismatchError
from billing.domain.product_mapping import REQUIRED_TARGET_TYPE_BY_PRODUCT
from billing.domain.value_objects import OrderStatus, ProductSnapshot, TargetRef
from shared_kernel import BusinessProfileId, Money

_TERMINAL_STATES = frozenset({OrderStatus.FULFILLED, OrderStatus.CANCELLED})


@dataclass(frozen=True)
class Order:
    """`lock_version` matches `backbone.persistence.AggregateMixin`'s optimistic-locking column
    (catalog's own `Listing.lock_version` precedent) -- domain code never reads or increments it;
    the ORM's `version_id_col` does that transparently on `UPDATE`."""

    id: UUID
    purchaser_profile_id: BusinessProfileId
    """The sole purchaser reference the Physical DB Design's own `purchase_order` column table
    carries -- no separate acting-account-id column exists there (unlike catalog's `Listing.
    owner_user_id`); every v1 purchase is business-profile-scoped (`Order.purchaserProfileId` is
    a required OpenAPI field, never nullable)."""
    product_snapshot: ProductSnapshot
    target: TargetRef
    amount: Money
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    lock_version: int = 0

    @staticmethod
    def create(
        *,
        order_id: UUID,
        purchaser_profile_id: BusinessProfileId,
        product_snapshot: ProductSnapshot,
        target: TargetRef,
        now: datetime,
    ) -> Order:
        """FR-SUBS-002: "creating a pending order." `amount` is copied verbatim from the frozen
        `product_snapshot.price` -- v1 has no discount/quantity concept, so an order's own price
        is always exactly its product's price at order time."""
        required_target_type = REQUIRED_TARGET_TYPE_BY_PRODUCT[product_snapshot.product_type]
        if target.target_type is not required_target_type:
            raise TargetTypeMismatchError(
                product_snapshot.product_type.value,
                required_target_type.value,
                target.target_type.value,
            )
        return Order(
            id=order_id,
            purchaser_profile_id=purchaser_profile_id,
            product_snapshot=product_snapshot,
            target=target,
            amount=product_snapshot.price,
            status=OrderStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

    def issue_invoice(self, *, now: datetime) -> Order:
        """FR-BILL-001: "generate an invoice for each purchase order" -- eager, at order
        placement (there is no separate OpenAPI operation to issue an invoice later); `application
        .order_use_cases.OrderUseCases.create_order` calls this in the same transaction as
        `create()`. `PENDING -> INVOICED` only. No `invoice_id` is recorded here: the Physical DB
        Design's own `purchase_order` column table carries no such column -- the FK points the
        other way (`invoice.purchase_order_id UNIQUE`, "the cheapest correct 1:1"). Callers that
        need "the invoice for this order" look it up via `InvoiceRepository.get_by_order_id`."""
        if self.status is not OrderStatus.PENDING:
            raise IllegalOrderStateTransitionError("issue_invoice", self.status.value)
        return replace(self, status=OrderStatus.INVOICED, updated_at=now)

    def mark_paid(self, *, now: datetime) -> Order:
        """The sanctioned synchronous transaction's own Order-side half (DB Architecture Sec 1.3:
        "Invoice→Paid + Order→Paid + Entitlement activation"). `INVOICED -> PAID` only -- an order
        with no invoice yet has nothing to confirm payment against."""
        if self.status is not OrderStatus.INVOICED:
            raise IllegalOrderStateTransitionError("mark_paid", self.status.value)
        return replace(self, status=OrderStatus.PAID, updated_at=now)

    def fulfill(self, *, now: datetime) -> Order:
        """`PAID -> FULFILLED` -- the documented terminal lifecycle stage (Domain Model Sec 5.8:
        "Pending → Invoiced → Paid → Fulfilled | Cancelled"). No document names what triggers
        this transition for any of the six product types (unlike catalog's `Listing`, billing's
        products grant an entitlement, not a physical/service delivery with its own completion
        signal) -- provided for lifecycle completeness per the documented state machine; no use
        case in this task calls it (flagged in `billing/README.md` "Known gaps", the same
        "capability exists, no caller wires it yet" pattern as catalog's own
        `ListingModerationPort`)."""
        if self.status is not OrderStatus.PAID:
            raise IllegalOrderStateTransitionError("fulfill", self.status.value)
        return replace(self, status=OrderStatus.FULFILLED, updated_at=now)

    def cancel(self, *, now: datetime) -> Order:
        """`PENDING | INVOICED -> CANCELLED`. A `PAID` order is never cancellable through this
        method (the entitlement it granted must be revoked instead, a distinct action on the
        `Entitlement` itself, never a retroactive rewrite of the order that funded it -- Physical
        DB's "terminal rows immutable" guard trigger backs this at the storage layer too)."""
        if self.status in _TERMINAL_STATES or self.status is OrderStatus.PAID:
            raise IllegalOrderStateTransitionError("cancel", self.status.value)
        return replace(self, status=OrderStatus.CANCELLED, updated_at=now)
