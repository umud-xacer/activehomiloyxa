"""catalog: add listing.awaiting_payment

Revision ID: a3f7c1e9b0d4
Revises: 6b496c3c6048
Create Date: 2026-08-23 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation needs an explicit `# approved-destructive:` marker
# (QG-09). An applied migration is never edited (AIR-14) -- corrections are a new migration.
#
# Listing paywall Phase 3 (2026-08-23): `Listing.awaiting_payment` (`catalog/domain/listing.py`'s
# own docstring) -- an orthogonal boolean, same shape as the existing `is_flagged` column (not a
# new `LifecycleState` value, no CHECK constraint of its own). `NOT NULL DEFAULT false` is safe on
# an already-populated table: every existing row becomes `false` (never awaiting payment), which
# is the correct historical value -- this feature did not exist when they were created.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f7c1e9b0d4"
down_revision: str | None = "6b496c3c6048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listing",
        sa.Column(
            "awaiting_payment",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema="catalog",
    )


def downgrade() -> None:  # approved-destructive: dev-only fresh-install rollback
    op.drop_column(
        "listing", "awaiting_payment", schema="catalog"
    )  # approved-destructive: fresh-install rollback
