"""billing: add entitlement.remaining_credits

Revision ID: d81f4b62a7e5
Revises: c4e91a6d3f27
Create Date: 2026-08-23 00:00:03.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation needs an explicit `# approved-destructive:` marker
# (QG-09). An applied migration is never edited (AIR-14) -- corrections are a new migration.
#
# Listing paywall Phase 4 (2026-08-23): `Entitlement.remaining_credits` (`billing/domain/
# entitlement.py`'s own docstring) -- nullable, no server_default (unlike most columns here):
# every entitlement row that exists before this migration is NOT a `LISTING_CREDIT_BALANCE`
# (that entitlement type didn't exist before Phase 1 of this same task), so `NULL` is the
# historically correct value for all of them regardless -- there is nothing to backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d81f4b62a7e5"
down_revision: str | None = "c4e91a6d3f27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "entitlement",
        sa.Column("remaining_credits", sa.Integer(), nullable=True),
        schema="billing",
    )
    op.create_check_constraint(
        "ck_entitlement_remaining_credits_non_negative",
        "entitlement",
        "remaining_credits IS NULL OR remaining_credits >= 0",
        schema="billing",
    )


def downgrade() -> None:  # approved-destructive: dev-only fresh-install rollback
    op.drop_constraint(
        "ck_entitlement_remaining_credits_non_negative",
        "entitlement",
        schema="billing",
        type_="check",
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "entitlement", "remaining_credits", schema="billing"
    )  # approved-destructive: fresh-install rollback
