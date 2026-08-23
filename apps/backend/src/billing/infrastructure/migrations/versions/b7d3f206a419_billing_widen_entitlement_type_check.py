"""billing: widen entitlement.entitlement_type CHECK

Revision ID: b7d3f206a419
Revises: 6c1e9f4a2d70
Create Date: 2026-08-23 00:00:01.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation needs an explicit `# approved-destructive:` marker
# (QG-09). An applied migration is never edited (AIR-14) -- corrections are a new migration.
#
# Listing paywall (2026-08-23): `billing.domain.value_objects.EntitlementType` gained two new
# values, `LISTING_PUBLICATION`/`LISTING_CREDIT_BALANCE`. Postgres cannot ALTER a CHECK
# constraint in place, so this drops and re-adds `ck_entitlement_entitlement_type` under the
# same name with the widened value list -- every value that satisfied the old constraint still
# satisfies the new one, so this is a safe widening, not a narrowing.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d3f206a419"
down_revision: str | None = "6c1e9f4a2d70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_entitlement_entitlement_type"
_OLD_VALUES = "'ACTIVE_SUBSCRIPTION', 'LISTING_PROMOTION', 'VERIFICATION_ELIGIBILITY', 'BANNER_SLOT_BOOKING'"
_NEW_VALUES = (
    "'ACTIVE_SUBSCRIPTION', 'LISTING_PROMOTION', 'VERIFICATION_ELIGIBILITY', "
    "'BANNER_SLOT_BOOKING', 'LISTING_PUBLICATION', 'LISTING_CREDIT_BALANCE'"
)


def upgrade() -> None:
    op.drop_constraint(
        _CONSTRAINT_NAME, "entitlement", schema="billing", type_="check"
    )  # approved-destructive: immediately re-added below with a widened (not narrowed) value list
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "entitlement",
        f"entitlement_type IN ({_NEW_VALUES})",
        schema="billing",
    )


def downgrade() -> (
    None
):  # approved-destructive: fails if any row already uses a new entitlement_type value
    op.drop_constraint(
        _CONSTRAINT_NAME, "entitlement", schema="billing", type_="check"
    )  # approved-destructive: narrowing rollback
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "entitlement",
        f"entitlement_type IN ({_OLD_VALUES})",
        schema="billing",
    )
