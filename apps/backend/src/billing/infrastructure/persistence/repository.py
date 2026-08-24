"""`SqlalchemyOrderRepository`/`SqlalchemyInvoiceRepository`/`SqlalchemyEntitlementRepository` --
implement `application.ports`' repositories against Postgres. Maps persistence-ignorant domain
aggregates to/from ORM rows (DB Architecture Sec 18 "mapping lives in infrastructure/"). Mirrors
`catalog.infrastructure.persistence.repository`'s cursor-pagination/`save()` patterns exactly.
"""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from billing.domain import (
    ActivationState,
    Entitlement,
    EntitlementType,
    Invoice,
    InvoiceStatus,
    Order,
    OrderStatus,
    ProductSnapshot,
    ProductType,
    PromotionKind,
    TargetRef,
    TargetType,
)
from billing.domain.value_objects import PaymentConfirmation
from billing.infrastructure.persistence.models import (
    EntitlementRow,
    InvoiceRow,
    PurchaseOrderRow,
)
from shared_kernel import BusinessProfileId, Money


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id)


# --- Order ----------------------------------------------------------------------------------


def _order_to_domain(row: PurchaseOrderRow) -> Order:
    snapshot = row.product_snapshot
    # `Range.lower`/`Range.upper` round-trip exactly through `TargetRef.__post_init__`'s own
    # `end > start` check -- no bound-inclusivity translation needed for the default `[)` range.
    booking_window = (
        (row.booking_window.lower, row.booking_window.upper)
        if row.booking_window is not None
        else None
    )
    return Order(
        id=row.id,
        purchaser_profile_id=BusinessProfileId(value=row.purchaser_profile_id),
        product_snapshot=ProductSnapshot(
            product_definition_id=row.product_definition_id,
            product_definition_version_id=row.product_definition_version_id,
            product_type=ProductType(snapshot["product_type"]),
            price=Money(amount=row.amount, currency=row.currency),
            term_days=snapshot.get("term_days"),
            quota=snapshot.get("quota"),
        ),
        target=TargetRef(
            target_type=TargetType(row.target_type),
            target_id=row.target_id,
            booking_window=booking_window,
        ),
        amount=Money(amount=row.amount, currency=row.currency),
        status=OrderStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
    )


def _order_row_kwargs(order: Order) -> dict[str, object]:
    return {
        "purchaser_profile_id": order.purchaser_profile_id.value,
        "product_definition_id": order.product_snapshot.product_definition_id,
        "product_definition_version_id": order.product_snapshot.product_definition_version_id,
        "product_snapshot": {
            "product_type": order.product_snapshot.product_type.value,
            "term_days": order.product_snapshot.term_days,
            "quota": order.product_snapshot.quota,
        },
        "target_type": order.target.target_type.value,
        "target_id": order.target.target_id,
        "booking_window": (
            Range(order.target.booking_window[0], order.target.booking_window[1])
            if order.target.booking_window is not None
            else None
        ),
        "amount": order.amount.amount,
        "currency": order.amount.currency,
        "status": order.status.value,
    }


class SqlalchemyOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, order_id: UUID) -> Order | None:
        row = await self._session.get(PurchaseOrderRow, order_id)
        return _order_to_domain(row) if row is not None else None

    async def add(self, order: Order) -> None:
        kwargs = _order_row_kwargs(order)
        self._session.add(
            PurchaseOrderRow(
                id=order.id,
                created_at=order.created_at,
                updated_at=order.updated_at,
                **kwargs,
            )
        )
        # P-20 fix (confirmed integration defect): the session factory this repository is always
        # constructed against runs with `autoflush=False` (backbone.persistence.engine.
        # make_session_factory), so `OrderUseCases.create_order`'s own real call sequence --
        # `add(order)` immediately followed by `save(order)` in the SAME transaction, once the
        # invoice has been issued -- would find no row via `save()`'s own `session.get()` (the
        # `add()` above is still only pending, never flushed) and raise `LookupError` on every
        # real order creation. Mirrors the identical fix already applied to
        # `SqlalchemyFallbackIndexRepository.upsert_document()`.
        await self._session.flush()

    async def save(self, order: Order) -> Order:
        row = await self._session.get(PurchaseOrderRow, order.id)
        if row is None:
            raise LookupError(f"PurchaseOrderRow {order.id} not found for save()")
        for key, value in _order_row_kwargs(order).items():
            setattr(row, key, value)
        row.updated_at = order.updated_at
        await self._session.flush()
        return _order_to_domain(row)

    async def list_by_purchaser(
        self, purchaser_profile_id: UUID, *, cursor: str | None, limit: int
    ) -> tuple[list[Order], str | None]:
        stmt = (
            select(PurchaseOrderRow)
            .where(PurchaseOrderRow.purchaser_profile_id == purchaser_profile_id)
            .order_by(PurchaseOrderRow.created_at, PurchaseOrderRow.id)
            .limit(limit + 1)
        )
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (PurchaseOrderRow.created_at > created_at)
                | ((PurchaseOrderRow.created_at == created_at) & (PurchaseOrderRow.id > row_id))
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
        return [_order_to_domain(row) for row in rows], next_cursor


# --- Invoice ----------------------------------------------------------------------------------


def _invoice_to_domain(row: InvoiceRow) -> Invoice:
    confirmation = (
        PaymentConfirmation(
            confirmed_by=row.payment_confirmed_by,
            confirmed_at=row.payment_confirmed_at,
            note=row.payment_note,
        )
        if row.payment_confirmed_by is not None and row.payment_confirmed_at is not None
        else None
    )
    return Invoice(
        id=row.id,
        order_id=row.purchase_order_id,
        invoice_number=row.invoice_number,
        amount=Money(amount=row.amount, currency=row.currency),
        status=InvoiceStatus(row.status),
        payment_confirmation=confirmation,
        issued_at=row.issued_at,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
    )


def _invoice_row_kwargs(invoice: Invoice) -> dict[str, object]:
    confirmation = invoice.payment_confirmation
    return {
        "purchase_order_id": invoice.order_id,
        "invoice_number": invoice.invoice_number,
        "amount": invoice.amount.amount,
        "currency": invoice.amount.currency,
        "status": invoice.status.value,
        "payment_confirmed_by": confirmation.confirmed_by if confirmation else None,
        "payment_confirmed_at": confirmation.confirmed_at if confirmation else None,
        "payment_note": confirmation.note if confirmation else None,
    }


class SqlalchemyInvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, invoice_id: UUID) -> Invoice | None:
        row = await self._session.get(InvoiceRow, invoice_id)
        return _invoice_to_domain(row) if row is not None else None

    async def get_by_order_id(self, order_id: UUID) -> Invoice | None:
        result = await self._session.execute(
            select(InvoiceRow).where(InvoiceRow.purchase_order_id == order_id)
        )
        row = result.scalar_one_or_none()
        return _invoice_to_domain(row) if row is not None else None

    async def add(self, invoice: Invoice) -> None:
        kwargs = _invoice_row_kwargs(invoice)
        self._session.add(
            InvoiceRow(
                id=invoice.id,
                issued_at=invoice.issued_at,
                updated_at=invoice.updated_at,
                **kwargs,
            )
        )

    async def save(self, invoice: Invoice) -> Invoice:
        row = await self._session.get(InvoiceRow, invoice.id)
        if row is None:
            raise LookupError(f"InvoiceRow {invoice.id} not found for save()")
        for key, value in _invoice_row_kwargs(invoice).items():
            setattr(row, key, value)
        row.updated_at = invoice.updated_at
        await self._session.flush()
        return _invoice_to_domain(row)

    async def list_all(
        self, *, status: str | None, cursor: str | None, limit: int
    ) -> tuple[list[Invoice], str | None]:
        stmt = select(InvoiceRow).order_by(InvoiceRow.issued_at, InvoiceRow.id).limit(limit + 1)
        if status is not None:
            stmt = stmt.where(InvoiceRow.status == status)
        if cursor is not None:
            issued_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (InvoiceRow.issued_at > issued_at)
                | ((InvoiceRow.issued_at == issued_at) & (InvoiceRow.id > row_id))
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].issued_at, rows[-1].id)
        return [_invoice_to_domain(row) for row in rows], next_cursor

    async def next_invoice_number(self) -> str:
        """`billing.invoice_number_seq` (Physical DB Design). No literal format string is
        documented anywhere in the approved documents -- `INV-<6-digit-zero-padded-sequence>` is
        a defensible, human-readable, collision-free choice (flagged in `billing/README.md`
        "Known gaps" as a judgment call, not a literal spec)."""
        result = await self._session.execute(text("SELECT nextval('billing.invoice_number_seq')"))
        seq_value = result.scalar_one()
        return f"INV-{seq_value:06d}"


# --- Entitlement ------------------------------------------------------------------------------


def _entitlement_to_domain(row: EntitlementRow) -> Entitlement:
    return Entitlement(
        id=row.id,
        order_id=row.purchase_order_id,
        entitlement_type=EntitlementType(row.entitlement_type),
        promotion_kind=PromotionKind(row.promotion_kind) if row.promotion_kind else None,
        target_id=row.target_id,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        activation_state=ActivationState(row.activation_state),
        created_at=row.created_at,
        updated_at=row.updated_at,
        remaining_credits=row.remaining_credits,
        lock_version=row.lock_version,
    )


def _entitlement_row_kwargs(entitlement: Entitlement) -> dict[str, object]:
    return {
        "purchase_order_id": entitlement.order_id,
        "entitlement_type": entitlement.entitlement_type.value,
        "promotion_kind": entitlement.promotion_kind.value if entitlement.promotion_kind else None,
        "target_id": entitlement.target_id,
        "valid_from": entitlement.valid_from,
        "valid_until": entitlement.valid_until,
        "activation_state": entitlement.activation_state.value,
        "remaining_credits": entitlement.remaining_credits,
    }


class SqlalchemyEntitlementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entitlement_id: UUID) -> Entitlement | None:
        row = await self._session.get(EntitlementRow, entitlement_id)
        return _entitlement_to_domain(row) if row is not None else None

    async def add(self, entitlement: Entitlement) -> None:
        kwargs = _entitlement_row_kwargs(entitlement)
        self._session.add(
            EntitlementRow(
                id=entitlement.id,
                created_at=entitlement.created_at,
                updated_at=entitlement.updated_at,
                **kwargs,
            )
        )

    async def save(self, entitlement: Entitlement) -> Entitlement:
        row = await self._session.get(EntitlementRow, entitlement.id)
        if row is None:
            raise LookupError(f"EntitlementRow {entitlement.id} not found for save()")
        for key, value in _entitlement_row_kwargs(entitlement).items():
            setattr(row, key, value)
        row.updated_at = entitlement.updated_at
        await self._session.flush()
        return _entitlement_to_domain(row)

    async def list_by_order_id(self, order_id: UUID) -> tuple[Entitlement, ...]:
        result = await self._session.execute(
            select(EntitlementRow).where(EntitlementRow.purchase_order_id == order_id)
        )
        return tuple(_entitlement_to_domain(row) for row in result.scalars().all())

    async def list_active_for_profile(
        self, purchaser_profile_id: UUID, *, active_only: bool
    ) -> tuple[Entitlement, ...]:
        stmt = (
            select(EntitlementRow)
            .join(
                PurchaseOrderRow,
                PurchaseOrderRow.id == EntitlementRow.purchase_order_id,
            )
            .where(PurchaseOrderRow.purchaser_profile_id == purchaser_profile_id)
            .order_by(EntitlementRow.created_at)
        )
        if active_only:
            stmt = stmt.where(EntitlementRow.activation_state == ActivationState.ACTIVE.value)
        result = await self._session.execute(stmt)
        return tuple(_entitlement_to_domain(row) for row in result.scalars().all())

    async def list_expiring_active(
        self, *, now: datetime, batch_size: int
    ) -> tuple[Entitlement, ...]:
        stmt = (
            select(EntitlementRow)
            .where(
                EntitlementRow.activation_state == ActivationState.ACTIVE.value,
                EntitlementRow.valid_until <= now,
            )
            .order_by(EntitlementRow.valid_until)
            .limit(batch_size)
        )
        result = await self._session.execute(stmt)
        return tuple(_entitlement_to_domain(row) for row in result.scalars().all())
