"""billing: widen provider_transaction.provider CHECK

Revision ID: c4e91a6d3f27
Revises: b7d3f206a419
Create Date: 2026-08-23 00:00:02.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation needs an explicit `# approved-destructive:` marker
# (QG-09). An applied migration is never edited (AIR-14) -- corrections are a new migration.
#
# Listing paywall Phase 2 (2026-08-23): a `MockAdapter`/`MockMerchantApi` (`billing/infrastructure/
# payment_gateway/mock.py`) needs its own `ProviderTransaction` rows (provider="MOCK"), mirroring
# how `ClickAdapter`/`PaymeAdapter` already use this same table. `ck_provider_transaction_provider`
# is short (32 chars, well under Postgres's 63-byte identifier limit) so -- unlike the
# `product_type` CHECK widen earlier this session -- no truncation-hash ambiguity applies here;
# the literal name is used verbatim on both sides, matching how `6c1e9f4a2d70` originally created
# it and how `b7d3f206a419` (this same session, `ck_entitlement_entitlement_type`, also short)
# already widened its sibling successfully.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e91a6d3f27"
down_revision: str | None = "b7d3f206a419"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_provider_transaction_provider"
_OLD_VALUES = "'PAYME', 'CLICK'"
_NEW_VALUES = "'PAYME', 'CLICK', 'MOCK'"


def upgrade() -> None:
    op.drop_constraint(
        _CONSTRAINT_NAME, "provider_transaction", schema="billing", type_="check"
    )  # approved-destructive: immediately re-added below with a widened (not narrowed) value list
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "provider_transaction",
        f"provider IN ({_NEW_VALUES})",
        schema="billing",
    )


def downgrade() -> (
    None
):  # approved-destructive: fails if any row already uses provider='MOCK'
    op.drop_constraint(
        _CONSTRAINT_NAME, "provider_transaction", schema="billing", type_="check"
    )  # approved-destructive: narrowing rollback
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "provider_transaction",
        f"provider IN ({_OLD_VALUES})",
        schema="billing",
    )
