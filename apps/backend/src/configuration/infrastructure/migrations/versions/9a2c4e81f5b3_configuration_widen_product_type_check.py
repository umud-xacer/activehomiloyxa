"""configuration: widen product_definition_version.product_type CHECK

Revision ID: 9a2c4e81f5b3
Revises: c93f1a55e7d2
Create Date: 2026-08-23 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation needs an explicit `# approved-destructive:` marker
# (QG-09). An applied migration is never edited (AIR-14) -- corrections are a new migration.
#
# Listing paywall (2026-08-23): `billing.domain.value_objects.ProductType` gained two new values,
# `LISTING_PUBLICATION`/`LISTING_CREDIT_PACK`. Postgres cannot ALTER a CHECK constraint in place,
# so this drops and re-adds the constraint with the widened value list -- every value that
# satisfied the old constraint still satisfies the new one, so this is a safe widening, not a
# narrowing.
#
# The original constraint's SQLAlchemy-generated name (`op.f("ck_product_definition_version_
# ck_product_definition_version_type")` in 3a5779ed6064, 64 raw characters) exceeds Postgres's
# 63-byte identifier limit, so SQLAlchemy's `conv()` truncation-with-hash kicked in at CREATE
# time -- and that hash is derived in a way this migration cannot reliably reproduce for an
# arbitrary already-existing database (confirmed live 2026-08-23: this file's first version
# hardcoded the hash this exact SQLAlchemy/dialect combination computes locally today,
# `..._ver_7397`, and it did not match production's already-existing `..._ver_983c` -- almost
# certainly because the table was first created under a different SQLAlchemy point release,
# which can change the truncation hash). Rather than hardcode any one hash (correct for exactly
# one environment's creation-time history), this looks the real name up from `pg_constraint` at
# migration run time -- a `product_type`-mentioning CHECK constraint on this table is unambiguous
# (the table's other three CHECK constraints are on `status`/`price_amount`/`validity_until`),
# so this is robust across every environment regardless of which hash it happens to carry.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a2c4e81f5b3"
down_revision: str | None = "c93f1a55e7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_product_definition_version_ck_product_definition_version_type"
_OLD_VALUES = "'BANNER_PLACEMENT','FEATURED','PREMIUM','SUBSCRIPTION','TOP_PLACEMENT','VERIFICATION'"
_NEW_VALUES = (
    "'BANNER_PLACEMENT','FEATURED','PREMIUM','SUBSCRIPTION','TOP_PLACEMENT','VERIFICATION',"
    "'LISTING_PUBLICATION','LISTING_CREDIT_PACK'"
)


def _find_product_type_check_name(conn: sa.Connection) -> str:
    row = conn.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'configuration.product_definition_version'::regclass "
            "AND contype = 'c' AND pg_get_constraintdef(oid) LIKE '%product_type%'"
        )
    ).fetchone()
    if row is None:
        raise RuntimeError(
            "could not find the product_type CHECK constraint on "
            "configuration.product_definition_version -- has it already been renamed?"
        )
    return str(row[0])


def upgrade() -> None:
    conn = op.get_bind()
    existing_name = _find_product_type_check_name(conn)
    op.execute(
        f'ALTER TABLE configuration.product_definition_version DROP CONSTRAINT "{existing_name}"'
    )  # approved-destructive: immediately re-added below with a widened (not narrowed) value list
    op.create_check_constraint(
        op.f(_CONSTRAINT_NAME),
        "product_definition_version",
        f"product_type IN ({_NEW_VALUES})",
        schema="configuration",
    )


def downgrade() -> (
    None
):  # approved-destructive: fails if any row already uses a new product_type value
    conn = op.get_bind()
    existing_name = _find_product_type_check_name(conn)
    op.execute(
        f'ALTER TABLE configuration.product_definition_version DROP CONSTRAINT "{existing_name}"'
    )  # approved-destructive: narrowing rollback
    op.create_check_constraint(
        op.f(_CONSTRAINT_NAME),
        "product_definition_version",
        f"product_type IN ({_OLD_VALUES})",
        schema="configuration",
    )
