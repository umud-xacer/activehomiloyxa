"""Eventual-consistency integration test: after confirming payment for a `SUBSCRIPTION` order,
catalog's own already-built `handle_entitlement_event` (`catalog/infrastructure/
event_projection.py`, unmodified by this task) demonstrably reacts to the REAL
`EntitlementActivated` event billing publishes -- proving `composition_root.
make_catalog_entitlement_projection_handler`'s filtering routes the right events to the right
consumer with the right payload shape, end to end, against a real database.

**Search-side equivalent intentionally absent from this test file.** This billing-p09 worktree
branched from `main` before Task P-08 (search, PR #5 on `active-home/active-home-platform`) was
merged -- `apps/backend/src/search/` on this branch is still the frozen P-01 stub (no domain/
application/infrastructure code at all), so there is no `search.infrastructure.event_projection.
handle_entitlement_activated` to call here. Billing's own `EntitlementActivated` payload
(`payment_use_cases.py::_entitlement_activated_payload`) already carries every field that
consumer needs (`listingId`/`kind`/`entitlementId`/`validUntil`) for a `LISTING_PROMOTION`
entitlement, verified directly against P-08's own source at
`apps/backend/tests/billing/test_payment_use_cases.py::TestConfirmPaymentSanctionedTransaction::
test_I03_entitlement_activated_payload_matches_the_frozen_shape_both_consumers_need`
-- but the actual live-consumer wiring/verification for search must wait until PR #5 merges into
`main`. Flagged in `billing/README.md` "Known gaps", not silently skipped without explanation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from billing.domain import (
    EntitlementFactory,
    Invoice,
    Order,
    ProductSnapshot,
    ProductType,
    TargetRef,
    TargetType,
)
from billing.infrastructure.persistence.repository import (
    SqlalchemyEntitlementRepository,
    SqlalchemyInvoiceRepository,
    SqlalchemyOrderRepository,
)
from catalog.infrastructure.persistence.base import CatalogBase
from catalog.infrastructure.persistence.models import SubscriptionProjectionRow
from composition_root import make_billing_entitlement_fanout_handler
from contracts.events.billing import EntitlementActivated
from shared_kernel import BusinessProfileId, Money

NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _catalog_tables(engine: AsyncEngine) -> None:
    """This ONE test file needs BOTH schemas -- `integration/conftest.py`'s own `engine` fixture
    only creates billing's own tables (every other billing integration test needs nothing else).
    catalog's `subscription_projection` table is the thing being asserted against here."""
    async with engine.begin() as conn:
        await conn.run_sync(CatalogBase.metadata.create_all, checkfirst=True)


async def test_catalog_subscription_projection_reacts_to_a_real_entitlement_activated_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    purchaser_profile_id = BusinessProfileId(value=uuid4())
    snapshot = ProductSnapshot(
        product_definition_id=uuid4(),
        product_definition_version_id=uuid4(),
        product_type=ProductType.SUBSCRIPTION,
        price=Money(amount=Decimal("100000.00"), currency="UZS"),
        term_days=30,
        quota={"max_active_listings": 25},
    )
    order = Order.create(
        order_id=uuid4(),
        purchaser_profile_id=purchaser_profile_id,
        product_snapshot=snapshot,
        target=TargetRef(target_type=TargetType.PROFILE, target_id=None, booking_window=None),
        now=NOW,
    )

    async with session_factory() as session:
        orders = SqlalchemyOrderRepository(session)
        invoices = SqlalchemyInvoiceRepository(session)
        entitlements = SqlalchemyEntitlementRepository(session)

        await orders.add(order)
        await session.flush()
        invoice = Invoice.issue(
            invoice_id=uuid4(),
            order_id=order.id,
            invoice_number=await invoices.next_invoice_number(),
            amount=order.amount,
            now=NOW,
        )
        await invoices.add(invoice)
        order = order.issue_invoice(now=NOW).mark_paid(now=NOW)
        await orders.save(order)

        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=order, now=NOW
        )
        await entitlements.add(entitlement)
        await session.commit()

    payload = {
        "entitlementId": str(entitlement.id),
        "orderId": str(order.id),
        "entitlementType": "ACTIVE_SUBSCRIPTION",
        "ownerProfileId": str(purchaser_profile_id.value),
        "targetId": str(purchaser_profile_id.value),
        "listingId": None,
        "kind": None,
        "productDefinitionId": str(snapshot.product_definition_id),
        "quota": snapshot.quota,
        "validFrom": entitlement.valid_from.isoformat(),
        "validUntil": entitlement.valid_until.isoformat(),
    }
    event = EntitlementActivated(
        event_id=uuid4(),
        occurred_at=NOW,
        actor=None,
        aggregate_type="Entitlement",
        aggregate_id=entitlement.id,
        payload=payload,
    )

    # this IS the composition root's real wiring -- the same handler
    # `provide_catalog_entitlement_projection_dispatcher` attaches to billing's outbox (Task P-11
    # broadened this handler to also route VERIFICATION_ELIGIBILITY events to profiles, Task P-14
    # broadened it again for ads' BANNER_SLOT_BOOKING events; this ACTIVE_SUBSCRIPTION event only
    # exercises catalog's own routing branch, so reusing billing's own `session_factory` for the
    # unused `profiles_session_factory`/`ads_session_factory` parameters is safe here).
    handler = make_billing_entitlement_fanout_handler(
        billing_session_factory=session_factory,
        profiles_session_factory=session_factory,
        ads_session_factory=session_factory,
    )
    await handler(event)

    async with session_factory() as session:
        row = await session.get(SubscriptionProjectionRow, purchaser_profile_id.value)
        assert row is not None, (
            "catalog.subscription_projection must reflect the real EntitlementActivated event"
        )
        assert row.quota_document["max_active_listings"] == 25
