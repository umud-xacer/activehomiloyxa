"""billing: add missing invoice.created_at column

Revision ID: 31a5840450ce
Revises: 1f9f2a35ab84
Create Date: 2026-07-15 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Fix (confirmed via a real DROP-SCHEMA-CASCADE + upgrade-head re-application of billing's
# migration chain against Postgres, surfaced while verifying the P-21 outbox-index migration):
# `InvoiceRow` mixes in `backbone.persistence.AggregateMixin`, which declares `created_at` on
# every aggregate-root table, but the original `2ed0cdddb299` migration's `create_table("invoice",
# ...)` call never included it -- `purchase_order` and `entitlement` (created in the same
# migration) both have it, `invoice` alone does not. This was masked in module-local billing
# tests, which build their schema via `BillingBase.metadata.create_all()` (reflecting the ORM
# model, not the migration DDL) rather than the real Alembic chain, so it never surfaced until a
# schema built purely from migrations was queried by a cross-module suite doing
# `SELECT ... RETURNING invoice.created_at` (SQLAlchemy's `eager_defaults=True`, P-20 fix).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "31a5840450ce"
down_revision: str | None = "1f9f2a35ab84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invoice",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="billing",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_column(
        "invoice", "created_at", schema="billing"
    )  # approved-destructive: fresh-install rollback
