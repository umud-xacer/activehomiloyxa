"""billing: create provider_transaction (ADR-0010, Payme/Click gateway integration)

Revision ID: 6c1e9f4a2d70
Revises: 31a5840450ce
Create Date: 2026-08-14 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# ADR-0010: `provider_transaction` is NOT in the documented Physical Database Design -- a
# locally-necessary table this task adds, the same precedent `profiles.subscription_entitlement_
# projection` set for the Monetization task. Tracks Payme/Click's own server-to-server
# transaction handshake state independently of `invoice`/`purchase_order`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c1e9f4a2d70"
down_revision: str | None = "31a5840450ce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_transaction",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_transaction_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="CREATED"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("performed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["billing.invoice.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "provider IN ('PAYME', 'CLICK')", name="ck_provider_transaction_provider"
        ),
        sa.CheckConstraint(
            "state IN ('CREATED', 'PERFORMED', 'CANCELLED')",
            name="ck_provider_transaction_state",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_transaction"),
        sa.UniqueConstraint(
            "provider", "provider_transaction_id", name="ux_provider_transaction_external_id"
        ),
        sa.UniqueConstraint(
            "invoice_id", "provider", name="ux_provider_transaction_invoice_provider"
        ),
        schema="billing",
    )
    op.create_index(
        "ix_provider_transaction_invoice_id",
        "provider_transaction",
        ["invoice_id"],
        schema="billing",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_index(
        "ix_provider_transaction_invoice_id", table_name="provider_transaction", schema="billing"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "provider_transaction", schema="billing"
    )  # approved-destructive: fresh-install rollback
