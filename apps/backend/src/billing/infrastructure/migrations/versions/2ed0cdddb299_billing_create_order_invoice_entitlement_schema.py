"""billing: create purchase_order, invoice, entitlement, outbox_event, processed_event

Revision ID: 2ed0cdddb299
Revises:
Create Date: 2026-07-12 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate` -- same reason as catalog's/search's first
# migrations: with `include_schemas=True` (Physical DB Sec 13), autogenerate against the shared
# dev database diffs against every schema it can see and proposes dropping already-applied tables
# from other modules. Written by hand against `billing.infrastructure.persistence.models`
# instead, kept in sync by manual `alembic upgrade head` / `alembic downgrade base` verification
# against a real database.
#
# `billing.purchase_order` (not `billing.order`) -- `order` is a SQL reserved word (PD-05 rename,
# Physical DB Design). `billing.invoice_number_seq` backs `InvoiceRepository.next_invoice_number`
# (FR-BILL-003: "formatted from billing.invoice_number_seq at issue") -- created here, alongside
# the tables, since it is exclusively `invoice`'s own concern.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2ed0cdddb299"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("billing",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE billing.invoice_number_seq")

    op.create_table(
        "purchase_order",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("purchaser_profile_id", sa.UUID(), nullable=False),
        sa.Column("product_definition_id", sa.UUID(), nullable=False),
        sa.Column("product_definition_version_id", sa.UUID(), nullable=False),
        sa.Column("product_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("booking_window", postgresql.TSTZRANGE(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.Text(), server_default="UZS", nullable=False),
        sa.Column("status", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('PROFILE', 'LISTING', 'SLOT_BOOKING')",
            name="ck_purchase_order_target_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'INVOICED', 'PAID', 'FULFILLED', 'CANCELLED')",
            name="ck_purchase_order_status",
        ),
        sa.CheckConstraint(
            "(target_type = 'SLOT_BOOKING') = (booking_window IS NOT NULL)",
            name="ck_purchase_order_booking_shape",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_purchase_order_amount_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_order"),
        schema="billing",
    )
    op.create_index(
        "ix_purchase_order_purchaser_profile_id",
        "purchase_order",
        ["purchaser_profile_id", "created_at"],
        schema="billing",
    )
    op.create_index(
        "ix_purchase_order_status",
        "purchase_order",
        ["status"],
        schema="billing",
        postgresql_where=sa.text("status IN ('PENDING', 'INVOICED')"),
    )

    op.create_table(
        "invoice",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("purchase_order_id", sa.UUID(), nullable=False),
        sa.Column("invoice_number", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.Text(), server_default="UZS", nullable=False),
        sa.Column("status", sa.Text(), server_default="ISSUED", nullable=False),
        sa.Column("payment_confirmed_by", sa.UUID(), nullable=True),
        sa.Column("payment_confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("payment_note", sa.Text(), nullable=True),
        sa.Column(
            "issued_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('ISSUED', 'PAID', 'VOID')", name="ck_invoice_status"),
        sa.CheckConstraint(
            "(status = 'PAID') = (payment_confirmed_by IS NOT NULL AND "
            "payment_confirmed_at IS NOT NULL)",
            name="ck_invoice_paid_shape",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["billing.purchase_order.id"],
            name="fk_invoice_purchase_order",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoice"),
        sa.UniqueConstraint("purchase_order_id", name="ux_invoice_purchase_order_id"),
        sa.UniqueConstraint("invoice_number", name="ux_invoice_invoice_number"),
        schema="billing",
    )

    op.create_table(
        "entitlement",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("purchase_order_id", sa.UUID(), nullable=False),
        sa.Column("entitlement_type", sa.Text(), nullable=False),
        sa.Column("promotion_kind", sa.Text(), nullable=True),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("activation_state", sa.Text(), server_default="ACTIVE", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "entitlement_type IN ('ACTIVE_SUBSCRIPTION', 'LISTING_PROMOTION', "
            "'VERIFICATION_ELIGIBILITY', 'BANNER_SLOT_BOOKING')",
            name="ck_entitlement_entitlement_type",
        ),
        sa.CheckConstraint(
            "promotion_kind IS NULL OR promotion_kind IN ('PREMIUM', 'FEATURED', 'TOP_PLACEMENT')",
            name="ck_entitlement_promotion_kind",
        ),
        sa.CheckConstraint(
            "(entitlement_type = 'LISTING_PROMOTION') = (promotion_kind IS NOT NULL)",
            name="ck_entitlement_promo_shape",
        ),
        sa.CheckConstraint(
            "activation_state IN ('ACTIVE', 'EXPIRED', 'REVOKED')",
            name="ck_entitlement_activation_state",
        ),
        sa.CheckConstraint("valid_until > valid_from", name="ck_entitlement_validity_ordering"),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["billing.purchase_order.id"],
            name="fk_entitlement_purchase_order",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_entitlement"),
        schema="billing",
    )
    op.create_index(
        "ix_entitlement_activation_state_valid_until",
        "entitlement",
        ["activation_state", "valid_until"],
        schema="billing",
        postgresql_where=sa.text("activation_state = 'ACTIVE'"),
    )
    op.create_index(
        "ix_entitlement_target_id",
        "entitlement",
        ["target_id"],
        schema="billing",
    )

    op.create_table(
        "outbox_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.UUID(), nullable=True),
        sa.Column("aggregate_type", sa.String(), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dispatch_status", sa.String(), server_default="PENDING", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("dispatched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dispatch_status IN ('PENDING', 'DISPATCHED', 'DEAD')",
            name="ck_outbox_event_dispatch_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_event"),
        schema="billing",
    )

    op.create_table(
        "processed_event",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("handler", sa.String(), nullable=False),
        sa.Column(
            "processed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("result", sa.String(), nullable=False),
        sa.CheckConstraint(
            "result IN ('APPLIED', 'SKIPPED', 'FAILED')", name="ck_processed_event_result"
        ),
        sa.PrimaryKeyConstraint("event_id", "handler", name="pk_processed_event"),
        schema="billing",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table("processed_event", schema="billing")  # approved-destructive: dev-only rollback
    op.drop_table("outbox_event", schema="billing")  # approved-destructive: fresh-install rollback
    op.drop_table("entitlement", schema="billing")  # approved-destructive: fresh-install rollback
    op.drop_table("invoice", schema="billing")  # approved-destructive: fresh-install rollback
    op.drop_table("purchase_order", schema="billing")  # approved-destructive: dev-only rollback
    op.execute(
        "DROP SEQUENCE billing.invoice_number_seq"
    )  # approved-destructive: fresh-install rollback
