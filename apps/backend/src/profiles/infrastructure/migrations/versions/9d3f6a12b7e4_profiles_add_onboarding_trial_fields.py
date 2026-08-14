"""profiles: add business_profile onboarding/trial fields (ADR-0010)

Revision ID: 9d3f6a12b7e4
Revises: a4c1f9e7d203
Create Date: 2026-08-14 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# ADR-0010: `onboarding_completed_at`/`trial_starts_at`/`trial_ends_at` are nullable, additive
# columns on `business_profile` -- the 5-day free-trial window a LEGAL_ENTITY owner starts by
# completing the mandatory onboarding wizard. See that ADR for why the trial is projected
# directly into the existing `subscription_entitlement_projection` table rather than modeled as
# a real billing `Entitlement`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d3f6a12b7e4"
down_revision: str | None = "a4c1f9e7d203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "business_profile",
        sa.Column("onboarding_completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="profiles",
    )
    op.add_column(
        "business_profile",
        sa.Column("trial_starts_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="profiles",
    )
    op.add_column(
        "business_profile",
        sa.Column("trial_ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="profiles",
    )
    op.create_check_constraint(
        "ck_trial_shape",
        "business_profile",
        "(trial_starts_at IS NULL) = (trial_ends_at IS NULL)",
        schema="profiles",
    )
    op.create_check_constraint(
        "ck_onboarding_implies_trial",
        "business_profile",
        "onboarding_completed_at IS NULL OR trial_starts_at IS NOT NULL",
        schema="profiles",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_constraint(
        "ck_onboarding_implies_trial", "business_profile", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_constraint(
        "ck_trial_shape", "business_profile", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "business_profile", "trial_ends_at", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "business_profile", "trial_starts_at", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "business_profile", "onboarding_completed_at", schema="profiles"
    )  # approved-destructive: fresh-install rollback
