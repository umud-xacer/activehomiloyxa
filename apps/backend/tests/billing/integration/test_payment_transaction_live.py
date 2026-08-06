"""Proves DB Architecture Sec 1.3's OTHER sanctioned synchronous exception: Invoice→Paid +
Order→Paid + Entitlement activation all commit in ONE transaction inside BC-08. A forced failure
between the three writes and the commit rolls ALL of them back together -- there is no partial
state where the invoice is paid but no entitlement exists, or the entitlement exists but the
order is still merely `INVOICED`. Mirrors `apps/backend/tests/catalog/integration/
test_transactional_outbox_live.py`'s own forced-failure pattern exactly, extended to three
aggregates instead of one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from billing.domain import (
    EntitlementFactory,
    Invoice,
    Order,
    ProductSnapshot,
    ProductType,
    TargetRef,
    TargetType,
)
from billing.infrastructure.persistence.models import EntitlementRow, OutboxEventRow
from billing.infrastructure.persistence.repository import (
    SqlalchemyEntitlementRepository,
    SqlalchemyInvoiceRepository,
    SqlalchemyOrderRepository,
)
from contracts.events.billing import EntitlementActivated, PaymentConfirmed
from shared_kernel import BusinessProfileId, Money

NOW = datetime(2026, 7, 12, tzinfo=UTC)


class _SimulatedFailure(Exception):
    pass


def _order() -> Order:
    snapshot = ProductSnapshot(
        product_definition_id=uuid4(),
        product_definition_version_id=uuid4(),
        product_type=ProductType.PREMIUM,
        price=Money(amount=Decimal("50000.00"), currency="UZS"),
        term_days=30,
        quota=None,
    )
    return Order.create(
        order_id=uuid4(),
        purchaser_profile_id=BusinessProfileId(value=uuid4()),
        product_snapshot=snapshot,
        target=TargetRef(target_type=TargetType.LISTING, target_id=uuid4(), booking_window=None),
        now=NOW,
    )


async def _seed_invoiced_order(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Order, Invoice]:
    order = _order()
    async with session_factory() as session:
        order_repo = SqlalchemyOrderRepository(session)
        invoice_repo = SqlalchemyInvoiceRepository(session)
        await order_repo.add(order)
        await session.flush()
        invoice_number = await invoice_repo.next_invoice_number()
        invoice = Invoice.issue(
            invoice_id=uuid4(),
            order_id=order.id,
            invoice_number=invoice_number,
            amount=order.amount,
            now=NOW,
        )
        await invoice_repo.add(invoice)
        invoiced_order = order.issue_invoice(now=NOW)
        await order_repo.save(invoiced_order)
        await session.commit()
    return invoiced_order, invoice


async def test_forced_failure_rolls_back_invoice_order_entitlement_and_both_outbox_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    order, invoice = await _seed_invoiced_order(session_factory)
    operator_id = uuid4()

    with pytest.raises(_SimulatedFailure):
        async with session_factory() as session:
            order_repo = SqlalchemyOrderRepository(session)
            invoice_repo = SqlalchemyInvoiceRepository(session)
            entitlement_repo = SqlalchemyEntitlementRepository(session)
            outbox = OutboxWriter(session, OutboxEventRow)

            loaded_invoice = await invoice_repo.get_by_id(invoice.id)
            assert loaded_invoice is not None
            confirmed_invoice = loaded_invoice.confirm_payment(
                confirmed_by=operator_id, note="cash", now=NOW
            )
            await invoice_repo.save(confirmed_invoice)

            loaded_order = await order_repo.get_by_id(order.id)
            assert loaded_order is not None
            paid_order = loaded_order.mark_paid(now=NOW)
            await order_repo.save(paid_order)

            entitlement = EntitlementFactory.activate_from_paid_order(
                entitlement_id=uuid4(), order=paid_order, now=NOW
            )
            await entitlement_repo.add(entitlement)

            await outbox.append(
                PaymentConfirmed(
                    event_id=uuid4(),
                    occurred_at=NOW,
                    actor=operator_id,
                    aggregate_type="Invoice",
                    aggregate_id=invoice.id,
                    payload={"invoiceId": str(invoice.id)},
                )
            )
            await outbox.append(
                EntitlementActivated(
                    event_id=uuid4(),
                    occurred_at=NOW,
                    actor=operator_id,
                    aggregate_type="Entitlement",
                    aggregate_id=entitlement.id,
                    payload={"entitlementId": str(entitlement.id)},
                )
            )
            await session.flush()  # all writes staged, nothing committed yet

            raise _SimulatedFailure("simulated failure before commit")
            await session.commit()  # pragma: no cover -- unreachable, documents intent

    async with session_factory() as session:
        order_repo = SqlalchemyOrderRepository(session)
        invoice_repo = SqlalchemyInvoiceRepository(session)

        reloaded_invoice = await invoice_repo.get_by_id(invoice.id)
        assert reloaded_invoice is not None
        assert reloaded_invoice.status.value == "ISSUED", "invoice must not have been paid"

        reloaded_order = await order_repo.get_by_id(order.id)
        assert reloaded_order is not None
        assert reloaded_order.status.value == "INVOICED", "order must not have been marked paid"

        entitlement_rows = (await session.execute(select(EntitlementRow))).scalars().all()
        assert entitlement_rows == [], "no entitlement must have survived"

        outbox_rows = (await session.execute(select(OutboxEventRow))).scalars().all()
        assert outbox_rows == [], "neither outbox row must have survived"


async def test_successful_commit_persists_all_three_aggregates_and_both_events_together(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    order, invoice = await _seed_invoiced_order(session_factory)
    operator_id = uuid4()

    async with session_factory() as session:
        order_repo = SqlalchemyOrderRepository(session)
        invoice_repo = SqlalchemyInvoiceRepository(session)
        entitlement_repo = SqlalchemyEntitlementRepository(session)
        outbox = OutboxWriter(session, OutboxEventRow)

        loaded_invoice = await invoice_repo.get_by_id(invoice.id)
        assert loaded_invoice is not None
        confirmed_invoice = loaded_invoice.confirm_payment(
            confirmed_by=operator_id, note="cash", now=NOW
        )
        await invoice_repo.save(confirmed_invoice)

        loaded_order = await order_repo.get_by_id(order.id)
        assert loaded_order is not None
        paid_order = loaded_order.mark_paid(now=NOW)
        await order_repo.save(paid_order)

        entitlement = EntitlementFactory.activate_from_paid_order(
            entitlement_id=uuid4(), order=paid_order, now=NOW
        )
        await entitlement_repo.add(entitlement)

        await outbox.append(
            PaymentConfirmed(
                event_id=uuid4(),
                occurred_at=NOW,
                actor=operator_id,
                aggregate_type="Invoice",
                aggregate_id=invoice.id,
                payload={"invoiceId": str(invoice.id)},
            )
        )
        await outbox.append(
            EntitlementActivated(
                event_id=uuid4(),
                occurred_at=NOW,
                actor=operator_id,
                aggregate_type="Entitlement",
                aggregate_id=entitlement.id,
                payload={"entitlementId": str(entitlement.id)},
            )
        )
        await session.commit()

    async with session_factory() as session:
        order_repo = SqlalchemyOrderRepository(session)
        invoice_repo = SqlalchemyInvoiceRepository(session)

        reloaded_invoice = await invoice_repo.get_by_id(invoice.id)
        assert reloaded_invoice is not None
        assert reloaded_invoice.status.value == "PAID"

        reloaded_order = await order_repo.get_by_id(order.id)
        assert reloaded_order is not None
        assert reloaded_order.status.value == "PAID"

        entitlement_rows = (await session.execute(select(EntitlementRow))).scalars().all()
        assert len(entitlement_rows) == 1
        assert entitlement_rows[0].activation_state == "ACTIVE"

        outbox_rows = (await session.execute(select(OutboxEventRow))).scalars().all()
        assert {row.event_type for row in outbox_rows} == {
            "PaymentConfirmed",
            "EntitlementActivated",
        }
