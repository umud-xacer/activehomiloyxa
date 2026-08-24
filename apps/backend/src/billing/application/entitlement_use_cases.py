"""billing/application -- `EntitlementUseCases` (Task P-09): `listMyEntitlements` and the
expiry sweep (FR-SUBS-004/I-15). `revoke` exists for lifecycle completeness (`Entitlement.
revoke`'s own docstring) but has no OpenAPI operation to call it from in v1 -- provided, not
wired to any router."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from billing.application.exceptions import EntitlementNotFoundError, OrderNotFoundError
from billing.application.ports import EntitlementRepository, OrderRepository
from billing.domain import Entitlement, EntitlementType, Order
from contracts.events.billing import EntitlementExpired, EntitlementRevoked
from shared_kernel import BusinessProfileId, OutboxPort


class EntitlementUseCases:
    def __init__(
        self,
        *,
        entitlements: EntitlementRepository,
        orders: OrderRepository,
        outbox: OutboxPort,
    ) -> None:
        self._entitlements = entitlements
        self._orders = orders
        self._outbox = outbox

    async def list_my_entitlements(
        self, *, purchaser_profile_id: BusinessProfileId, active_only: bool
    ) -> tuple[Entitlement, ...]:
        return await self._entitlements.list_active_for_profile(
            purchaser_profile_id.value, active_only=active_only
        )

    async def sweep_expired(self, *, now: datetime, batch_size: int) -> int:
        """FR-SUBS-004: "the system SHALL track entitlement validity and SHALL deactivate
        entitlements at end of term." Called by `infrastructure.worker.EntitlementExpiryWorker`.
        Each entitlement's state change and its `EntitlementExpired` outbox row commit together
        (DEC-09) -- not the three-aggregate sanctioned exception (that is `confirm_payment`'s own,
        scoped there only): a sweep touches exactly one `Entitlement` per iteration."""
        expiring = await self._entitlements.list_expiring_active(now=now, batch_size=batch_size)
        for entitlement in expiring:
            order = await self._orders.get_by_id(entitlement.order_id)
            if order is None:
                raise OrderNotFoundError(entitlement.order_id)
            expired = entitlement.expire(now=now)
            await self._entitlements.save(expired)
            await self._outbox.append(
                EntitlementExpired(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=None,
                    aggregate_type="Entitlement",
                    aggregate_id=expired.id,
                    payload=_entitlement_lifecycle_payload(expired, order),
                )
            )
        return len(expiring)

    async def consume_listing_credit(
        self, *, purchaser_profile_id: BusinessProfileId, now: datetime
    ) -> Entitlement | None:
        """Listing paywall Phase 4 (2026-08-23): spends one listing-publish credit from the
        purchaser's earliest-expiring active `LISTING_CREDIT_BALANCE` entitlement, or None if
        none is eligible (a `remaining_credits` of `0` disqualifies a pack; `None` --
        unlimited -- never does). Returns the updated `Entitlement` on success, `None` on
        exhaustion -- the caller (`catalog`'s `CreditBalancePort` bridge) maps that directly to
        `requires_payment=True`.

        Deliberately mints no `Order`/`Invoice`: spending an already-paid-for credit is not a new
        purchase -- the original pack purchase is already the full audit trail, and a synthetic
        zero-amount `Order` would misrepresent what was actually charged. No outbox event either
        (nothing downstream projects "a credit was spent"; the listing's own `ListingPublished`
        event, fired by the caller after this returns, is the observable consequence)."""
        candidates = await self._entitlements.list_active_for_profile(
            purchaser_profile_id.value, active_only=True
        )
        eligible = sorted(
            (
                e
                for e in candidates
                if e.entitlement_type is EntitlementType.LISTING_CREDIT_BALANCE
                and (e.remaining_credits is None or e.remaining_credits > 0)
            ),
            key=lambda e: e.valid_until,
        )
        if not eligible:
            return None
        consumed = eligible[0].consume_credit(now=now)
        return await self._entitlements.save(consumed)

    async def revoke(self, entitlement_id: UUID, *, now: datetime) -> Entitlement:
        entitlement = await self._entitlements.get_by_id(entitlement_id)
        if entitlement is None:
            raise EntitlementNotFoundError(entitlement_id)
        order = await self._orders.get_by_id(entitlement.order_id)
        if order is None:
            raise OrderNotFoundError(entitlement.order_id)
        revoked = entitlement.revoke(now=now)
        revoked = await self._entitlements.save(revoked)
        await self._outbox.append(
            EntitlementRevoked(
                event_id=uuid4(),
                occurred_at=now,
                actor=None,
                aggregate_type="Entitlement",
                aggregate_id=revoked.id,
                payload=_entitlement_lifecycle_payload(revoked, order),
            )
        )
        return revoked


def _entitlement_lifecycle_payload(entitlement: Entitlement, order: Order) -> dict[str, object]:
    is_promotion = entitlement.promotion_kind is not None
    return {
        "entitlementId": str(entitlement.id),
        "orderId": str(order.id),
        "entitlementType": entitlement.entitlement_type.value,
        "ownerProfileId": str(order.purchaser_profile_id.value),
        "targetId": str(entitlement.target_id),
        "listingId": str(entitlement.target_id) if is_promotion else None,
        "kind": entitlement.promotion_kind.value if entitlement.promotion_kind else None,
    }
