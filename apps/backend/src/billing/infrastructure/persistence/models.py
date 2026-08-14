"""SQLAlchemy models for billing's Postgres-backed `Order`/`Invoice`/`Entitlement` aggregates
(Physical DB Design Sec 2.8 "billing schema"). `PurchaseOrderRow` is `billing.purchase_order` --
`order` is a SQL reserved word (PD-05 rename, Physical DB Design Sec "PD-05"). `InvoiceRow.
purchase_order_id` carries the 1:1 FK + UNIQUE constraint (not a reciprocal column on
`PurchaseOrderRow`) -- "the cheapest correct 1:1" (Physical DB Design's own words).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backbone.idempotency import make_processed_event_model
from backbone.outbox import make_outbox_event_model
from backbone.persistence import AggregateMixin
from billing.infrastructure.persistence.base import BillingBase

_TARGET_TYPES = "('PROFILE', 'LISTING', 'SLOT_BOOKING')"
_ORDER_STATUSES = "('PENDING', 'INVOICED', 'PAID', 'FULFILLED', 'CANCELLED')"
_INVOICE_STATUSES = "('ISSUED', 'PAID', 'VOID')"
_ENTITLEMENT_TYPES = (
    "('ACTIVE_SUBSCRIPTION', 'LISTING_PROMOTION', 'VERIFICATION_ELIGIBILITY', "
    "'BANNER_SLOT_BOOKING')"
)
_PROMOTION_KINDS = "('PREMIUM', 'FEATURED', 'TOP_PLACEMENT')"
_ACTIVATION_STATES = "('ACTIVE', 'EXPIRED', 'REVOKED')"
_PROVIDERS = "('PAYME', 'CLICK')"
_PROVIDER_TRANSACTION_STATES = "('CREATED', 'PERFORMED', 'CANCELLED')"


class PurchaseOrderRow(BillingBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "purchase_order"

    purchaser_profile_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_definition_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_definition_version_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    product_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """The frozen `ProductSnapshot` (I-07) -- `product_type`/`price`/`term_days`/`quota` as of
    order time, never re-read from `configuration`."""
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    booking_window: Mapped[Any | None] = mapped_column(TSTZRANGE, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="UZS")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")

    __table_args__ = (
        CheckConstraint(f"target_type IN {_TARGET_TYPES}", name="ck_purchase_order_target_type"),
        CheckConstraint(f"status IN {_ORDER_STATUSES}", name="ck_purchase_order_status"),
        CheckConstraint(
            "(target_type = 'SLOT_BOOKING') = (booking_window IS NOT NULL)",
            name="ck_purchase_order_booking_shape",
        ),
        CheckConstraint("amount >= 0", name="ck_purchase_order_amount_non_negative"),
    )


class InvoiceRow(BillingBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "invoice"

    purchase_order_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("billing.purchase_order.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="UZS")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="ISSUED")
    payment_confirmed_by: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    payment_confirmed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    payment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("purchase_order_id", name="ux_invoice_purchase_order_id"),
        UniqueConstraint("invoice_number", name="ux_invoice_invoice_number"),
        CheckConstraint(f"status IN {_INVOICE_STATUSES}", name="ck_invoice_status"),
        CheckConstraint(
            "(status = 'PAID') = (payment_confirmed_by IS NOT NULL AND "
            "payment_confirmed_at IS NOT NULL)",
            name="ck_invoice_paid_shape",
        ),
    )


class EntitlementRow(BillingBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "entitlement"

    purchase_order_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("billing.purchase_order.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entitlement_type: Mapped[str] = mapped_column(Text, nullable=False)
    promotion_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    activation_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="ACTIVE")

    __table_args__ = (
        CheckConstraint(
            f"entitlement_type IN {_ENTITLEMENT_TYPES}", name="ck_entitlement_entitlement_type"
        ),
        CheckConstraint(
            f"promotion_kind IS NULL OR promotion_kind IN {_PROMOTION_KINDS}",
            name="ck_entitlement_promotion_kind",
        ),
        CheckConstraint(
            "(entitlement_type = 'LISTING_PROMOTION') = (promotion_kind IS NOT NULL)",
            name="ck_entitlement_promo_shape",
        ),
        CheckConstraint(
            f"activation_state IN {_ACTIVATION_STATES}", name="ck_entitlement_activation_state"
        ),
        CheckConstraint("valid_until > valid_from", name="ck_entitlement_validity_ordering"),
    )


class ProviderTransactionRow(BillingBase):  # type: ignore[misc,valid-type]
    """ADR-0010. NOT an aggregate (no `AggregateMixin`) -- Payme/Click's own server-to-server
    transaction handshake state, tracked independently of `Invoice`/`Order` because a provider
    transaction can exist (`CREATED`) or be cancelled entirely without our own `Invoice` ever
    reaching `PAID`: Payme's protocol creates its own transaction record via `CreateTransaction`
    *before* `PerformTransaction` ever runs, and can `CancelTransaction` before or after that
    point. `PaymentUseCases.confirm_payment` (the sanctioned Invoice/Order/Entitlement
    transaction) is only ever called once, at the `PERFORMED` transition -- see
    `billing.infrastructure.payment_gateway`."""

    __tablename__ = "provider_transaction"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    invoice_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("billing.invoice.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_transaction_id: Mapped[str] = mapped_column(Text, nullable=False)
    """The provider's OWN transaction identifier (Payme's `id` param / Click's `click_trans_id`)
    -- distinct from this row's own `id`, which is generated by us at `CreateTransaction`/
    `Prepare` time."""
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="CREATED")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    performed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"provider IN {_PROVIDERS}", name="ck_provider_transaction_provider"),
        CheckConstraint(
            f"state IN {_PROVIDER_TRANSACTION_STATES}", name="ck_provider_transaction_state"
        ),
        UniqueConstraint(
            "provider", "provider_transaction_id", name="ux_provider_transaction_external_id"
        ),
        UniqueConstraint("invoice_id", "provider", name="ux_provider_transaction_invoice_provider"),
    )


OutboxEventRow: Any = make_outbox_event_model(BillingBase)
ProcessedEventRow: Any = make_processed_event_model(BillingBase)
