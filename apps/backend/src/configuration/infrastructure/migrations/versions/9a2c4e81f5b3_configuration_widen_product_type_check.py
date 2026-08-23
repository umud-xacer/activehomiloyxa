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
# so this drops and re-adds `ck_product_definition_version_ck_product_definition_version_type`
# under the same name with the widened value list -- every value that satisfied the old
# constraint still satisfies the new one, so this is a safe widening, not a narrowing.
"""

from __future__ import annotations

from collections.abc import Sequence

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


def upgrade() -> None:
    op.drop_constraint(
        _CONSTRAINT_NAME,
        "product_definition_version",
        schema="configuration",
        type_="check",
    )  # approved-destructive: immediately re-added below with a widened (not narrowed) value list
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "product_definition_version",
        f"product_type IN ({_NEW_VALUES})",
        schema="configuration",
    )


def downgrade() -> (
    None
):  # approved-destructive: fails if any row already uses a new product_type value
    op.drop_constraint(
        _CONSTRAINT_NAME,
        "product_definition_version",
        schema="configuration",
        type_="check",
    )  # approved-destructive: narrowing rollback
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "product_definition_version",
        f"product_type IN ({_OLD_VALUES})",
        schema="configuration",
    )
