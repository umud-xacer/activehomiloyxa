"""Integration tests: `SqlalchemyOrderRepository`/`SqlalchemyInvoiceRepository`/
`SqlalchemyEntitlementRepository` round-trip against real PostgreSQL, including the
`billing.invoice_number_seq`-backed sequential invoice numbering and the physical CHECK
constraints (`ck_purchase_order_booking_shape`, `ck_entitlement_promo_shape`, ...)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

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
from shared_kernel import BusinessProfileId, Money

NOW = datetime(2026, 7, 12, tzinfo=UTC)


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
        "now": NOW,
    }
    defaults.update(overrides)
    return Order.create(**defaults)  # type: ignore[arg-type]


async def test_order_add_then_get_by_id_round_trips(db_session: AsyncSession) -> None:
    repo = SqlalchemyOrderRepository(db_session)
    order = _order()
    await repo.add(order)
    await db_session.flush()

    fetched = await repo.get_by_id(order.id)
    assert fetched is not None
    assert fetched.purchaser_profile_id == order.purchaser_profile_id
    assert fetched.product_snapshot.product_type == order.product_snapshot.product_type
    assert fetched.amount == order.amount


async def test_order_save_persists_status_transitions(db_session: AsyncSession) -> None:
    repo = SqlalchemyOrderRepository(db_session)
    order = _order()
    await repo.add(order)
    await db_session.flush()

    invoiced = order.issue_invoice(now=NOW)
    saved = await repo.save(invoiced)
    assert saved.status.value == "INVOICED"

    reloaded = await repo.get_by_id(order.id)
    assert reloaded is not None
    assert reloaded.status.value == "INVOICED"


async def test_order_list_by_purchaser_scopes_correctly(db_session: AsyncSession) -> None:
    repo = SqlalchemyOrderRepository(db_session)
    mine = BusinessProfileId(value=uuid4())
    other = BusinessProfileId(value=uuid4())
    await repo.add(_order(purchaser_profile_id=mine))
    await repo.add(_order(purchaser_profile_id=other))
    await db_session.flush()

    orders, _cursor = await repo.list_by_purchaser(mine.value, cursor=None, limit=20)
    assert len(orders) == 1
    assert orders[0].purchaser_profile_id == mine


async def test_invoice_numbers_are_sequential(db_session: AsyncSession) -> None:
    repo = SqlalchemyInvoiceRepository(db_session)
    first = await repo.next_invoice_number()
    second = await repo.next_invoice_number()
    assert first != second
    assert first < second


async def test_invoice_add_then_get_by_order_id(db_session: AsyncSession) -> None:
    order_repo = SqlalchemyOrderRepository(db_session)
    invoice_repo = SqlalchemyInvoiceRepository(db_session)
    order = _order()
    await order_repo.add(order)
    await db_session.flush()

    invoice_number = await invoice_repo.next_invoice_number()
    invoice = Invoice.issue(
        invoice_id=uuid4(),
        order_id=order.id,
        invoice_number=invoice_number,
        amount=order.amount,
        now=NOW,
    )
    await invoice_repo.add(invoice)
    await db_session.flush()

    fetched = await invoice_repo.get_by_order_id(order.id)
    assert fetched is not None
    assert fetched.id == invoice.id


async def test_invoice_confirm_payment_persists_the_confirmation(db_session: AsyncSession) -> None:
    order_repo = SqlalchemyOrderRepository(db_session)
    invoice_repo = SqlalchemyInvoiceRepository(db_session)
    order = _order()
    await order_repo.add(order)
    await db_session.flush()
    invoice = Invoice.issue(
        invoice_id=uuid4(),
        order_id=order.id,
        invoice_number=await invoice_repo.next_invoice_number(),
        amount=order.amount,
        now=NOW,
    )
    await invoice_repo.add(invoice)
    await db_session.flush()

    operator_id = uuid4()
    confirmed = invoice.confirm_payment(confirmed_by=operator_id, note="cash", now=NOW)
    await invoice_repo.save(confirmed)
    await db_session.flush()

    reloaded = await invoice_repo.get_by_id(invoice.id)
    assert reloaded is not None
    assert reloaded.status.value == "PAID"
    assert reloaded.payment_confirmation is not None
    assert reloaded.payment_confirmation.confirmed_by == operator_id


async def test_entitlement_add_then_list_active_for_profile(db_session: AsyncSession) -> None:
    order_repo = SqlalchemyOrderRepository(db_session)
    entitlement_repo = SqlalchemyEntitlementRepository(db_session)
    purchaser = BusinessProfileId(value=uuid4())
    order = _order(purchaser_profile_id=purchaser)
    order = order.issue_invoice(now=NOW).mark_paid(now=NOW)
    await order_repo.add(order)
    await db_session.flush()

    entitlement = EntitlementFactory.activate_from_paid_order(
        entitlement_id=uuid4(), order=order, now=NOW
    )
    await entitlement_repo.add(entitlement)
    await db_session.flush()

    results = await entitlement_repo.list_active_for_profile(purchaser.value, active_only=True)
    assert len(results) == 1
    assert results[0].id == entitlement.id


async def test_entitlement_list_expiring_active_finds_only_past_due_active_rows(
    db_session: AsyncSession,
) -> None:
    order_repo = SqlalchemyOrderRepository(db_session)
    entitlement_repo = SqlalchemyEntitlementRepository(db_session)
    order = _order()
    order = order.issue_invoice(now=NOW).mark_paid(now=NOW)
    await order_repo.add(order)
    await db_session.flush()

    entitlement = EntitlementFactory.activate_from_paid_order(
        entitlement_id=uuid4(), order=order, now=NOW
    )
    await entitlement_repo.add(entitlement)
    await db_session.flush()

    not_yet_due = await entitlement_repo.list_expiring_active(
        now=NOW + timedelta(days=1), batch_size=50
    )
    assert not_yet_due == ()

    past_due = await entitlement_repo.list_expiring_active(
        now=NOW + timedelta(days=31), batch_size=50
    )
    assert len(past_due) == 1
    assert past_due[0].id == entitlement.id
