"""profiles: add sub_category to business_profile

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-08-19 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Additive, nullable TEXT column + CHECK (Organizations Sub-Category task, site-owner spec): a
# finer classification *within* one of the six `main_category` sectors (e.g. "Tijorat banki" vs.
# "Ipoteka markazi", both under FINANCE_MORTGAGE), for the public /companies directory's
# secondary filter dropdown and card chip. Nullable, and stays nullable even going forward --
# unlike `main_category`, the onboarding wizard does not require this field
# (`BusinessProfile.complete_onboarding` is untouched by this migration). The CHECK below only
# enforces membership in the flat union of all 24 legal codes across every main category, the
# same shallow membership check `ck_business_profile_main_category` does for its own column --
# the *cross-field* rule ("this code belongs to that profile's main_category") is a domain-layer
# invariant (`profiles.domain.business_profile._require_valid_sub_category`), not something this
# migration expresses at the database level.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUB_CATEGORIES = (
    "('COMMERCIAL_BANK', 'MORTGAGE_CENTER', 'MICROFINANCE', 'INSURANCE', 'LEASING', "
    "'GENERAL_CONTRACTOR', 'SUBCONTRACTOR', 'CIVIL_ENGINEERING', 'RENOVATION_CONTRACTOR', "
    "'INFRASTRUCTURE_CONSTRUCTION', "
    "'BUILDING_MATERIALS_MANUFACTURER', 'FURNITURE_MANUFACTURER', 'METAL_PRODUCTS_MANUFACTURER', "
    "'CONCRETE_CEMENT_MANUFACTURER', 'GLASS_ALUMINUM_MANUFACTURER', "
    "'ARCHITECTURE_STUDIO', 'INTERIOR_DESIGN_STUDIO', 'LANDSCAPE_DESIGN_STUDIO', "
    "'ENGINEERING_DESIGN_STUDIO', "
    "'HOME_REPAIR_SERVICE', 'PLUMBING_ELECTRICAL_SERVICE', 'CLEANING_SERVICE', "
    "'APPLIANCE_REPAIR_SERVICE', "
    "'RESIDENTIAL_AGENCY', 'COMMERCIAL_AGENCY', 'PROPERTY_MANAGEMENT', 'VALUATION_SERVICE')"
)


def upgrade() -> None:
    op.add_column(
        "business_profile",
        sa.Column("sub_category", sa.Text(), nullable=True),
        schema="profiles",
    )
    op.create_check_constraint(
        "ck_business_profile_sub_category",
        "business_profile",
        f"sub_category IS NULL OR sub_category IN {_SUB_CATEGORIES}",
        schema="profiles",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_business_profile_sub_category", "business_profile", schema="profiles", type_="check"
    )
    op.drop_column("business_profile", "sub_category", schema="profiles")
