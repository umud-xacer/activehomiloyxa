"""profiles: add main_category to business_profile

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-17 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Additive, nullable TEXT column + CHECK (Organizations Main-Category task, site-owner spec): a
# six-value sector classification for the public /companies directory's category tabs. Nullable
# so every pre-existing row backfills to NULL with no data migration needed; the onboarding
# wizard enforces it as mandatory going forward at the domain layer, not via a DB NOT NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MAIN_CATEGORIES = (
    "('FINANCE_MORTGAGE', 'CONSTRUCTION_CONTRACTORS', 'MANUFACTURERS_MATERIALS', "
    "'ARCHITECTURE_INTERIOR', 'REPAIR_SERVICES', 'REAL_ESTATE_AGENCIES')"
)


def upgrade() -> None:
    op.add_column(
        "business_profile",
        sa.Column("main_category", sa.Text(), nullable=True),
        schema="profiles",
    )
    op.create_check_constraint(
        "ck_business_profile_main_category",
        "business_profile",
        f"main_category IS NULL OR main_category IN {_MAIN_CATEGORIES}",
        schema="profiles",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_business_profile_main_category", "business_profile", schema="profiles", type_="check"
    )
    op.drop_column("business_profile", "main_category", schema="profiles")
