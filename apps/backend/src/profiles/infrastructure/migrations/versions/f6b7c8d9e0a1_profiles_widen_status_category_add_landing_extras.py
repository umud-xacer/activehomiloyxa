"""profiles: widen status/main_category/sub_category checks, add landing-page extras

Revision ID: f6b7c8d9e0a1
Revises: e4f5a6b7c8d9
Create Date: 2026-08-25 12:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation needs an explicit `# approved-destructive: <reason>`
# marker (QG-09, forward-looking window only -- never place the marker before the flagged line).
# An applied migration is never edited (AIR-14) -- corrections are a new migration.
#
# B2B Directory professional-upgrade task (ADR-0012, site-owner spec) does three additive things
# in one migration, all touching `profiles.business_profile`:
#   1. Widens `ck_business_profile_status` CREATED/ACTIVE/ARCHIVED -> +PENDING_REVIEW/+REJECTED
#      (the new registration-approval gate -- `profiles.domain.value_objects.ProfileStatus`).
#   2. Widens `ck_business_profile_main_category`/`ck_business_profile_sub_category` from 6/27
#      sectors to 10/47 (Transport & Logistics, Legal/Consulting/Accounting, Home Appliances &
#      Equipment, Hospitality Services, and their 20 new sub-categories).
#   3. Adds two new nullable columns (`finance_offer_details_localized` jsonb,
#      `promo_video_youtube_url` text) for the landing page's finance-terms block and YouTube
#      promo embed -- no CHECK constraint needed, both are free-form/host-validated at the
#      application layer, same "domain/interfaces decide, column stays permissive" split every
#      sibling additive field on this table already uses.
# Postgres cannot ALTER a CHECK constraint in place, so #1/#2 drop and re-add each constraint
# under the same name with a widened value list -- every value that satisfied the old constraint
# still satisfies the new one, so this is a safe widening, not a narrowing (same pattern as
# catalog's own `d4e1a9c2f6b7_catalog_widen_lifecycle_and_transition_checks.py`, this session).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f6b7c8d9e0a1"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_CONSTRAINT = "ck_business_profile_status"
_STATUS_OLD_VALUES = "('CREATED', 'ACTIVE', 'ARCHIVED')"
_STATUS_NEW_VALUES = "('CREATED', 'PENDING_REVIEW', 'ACTIVE', 'REJECTED', 'ARCHIVED')"

_MAIN_CATEGORY_CONSTRAINT = "ck_business_profile_main_category"
_MAIN_CATEGORY_OLD_VALUES = (
    "('FINANCE_MORTGAGE', 'CONSTRUCTION_CONTRACTORS', 'MANUFACTURERS_MATERIALS', "
    "'ARCHITECTURE_INTERIOR', 'REPAIR_SERVICES', 'REAL_ESTATE_AGENCIES')"
)
_MAIN_CATEGORY_NEW_VALUES = (
    "('FINANCE_MORTGAGE', 'CONSTRUCTION_CONTRACTORS', 'MANUFACTURERS_MATERIALS', "
    "'ARCHITECTURE_INTERIOR', 'REPAIR_SERVICES', 'REAL_ESTATE_AGENCIES', "
    "'TRANSPORT_LOGISTICS', 'LEGAL_CONSULTING_ACCOUNTING', 'HOME_APPLIANCES_EQUIPMENT', "
    "'HOSPITALITY_SERVICES')"
)

_SUB_CATEGORY_CONSTRAINT = "ck_business_profile_sub_category"
_SUB_CATEGORY_OLD_VALUES = (
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
_SUB_CATEGORY_NEW_VALUES = (
    "('COMMERCIAL_BANK', 'MORTGAGE_CENTER', 'MICROFINANCE', 'INSURANCE', 'LEASING', "
    "'GENERAL_CONTRACTOR', 'SUBCONTRACTOR', 'CIVIL_ENGINEERING', 'RENOVATION_CONTRACTOR', "
    "'INFRASTRUCTURE_CONSTRUCTION', "
    "'BUILDING_MATERIALS_MANUFACTURER', 'FURNITURE_MANUFACTURER', 'METAL_PRODUCTS_MANUFACTURER', "
    "'CONCRETE_CEMENT_MANUFACTURER', 'GLASS_ALUMINUM_MANUFACTURER', "
    "'ARCHITECTURE_STUDIO', 'INTERIOR_DESIGN_STUDIO', 'LANDSCAPE_DESIGN_STUDIO', "
    "'ENGINEERING_DESIGN_STUDIO', "
    "'HOME_REPAIR_SERVICE', 'PLUMBING_ELECTRICAL_SERVICE', 'CLEANING_SERVICE', "
    "'APPLIANCE_REPAIR_SERVICE', "
    "'RESIDENTIAL_AGENCY', 'COMMERCIAL_AGENCY', 'PROPERTY_MANAGEMENT', 'VALUATION_SERVICE', "
    "'FREIGHT_TRANSPORT', 'COURIER_DELIVERY', 'CAR_RENTAL', 'LOGISTICS_WAREHOUSING', "
    "'MOVING_SERVICES', "
    "'LAW_FIRM', 'ACCOUNTING_FIRM', 'BUSINESS_CONSULTING', 'TAX_ADVISORY', 'NOTARY_SERVICES', "
    "'HOME_APPLIANCE_STORE', 'ELECTRONICS_RETAILER', 'APPLIANCE_SERVICE_CENTER', "
    "'EQUIPMENT_RENTAL', 'HVAC_EQUIPMENT_SUPPLIER', "
    "'HOTEL_OPERATOR', 'GUESTHOUSE_OPERATOR', 'EVENT_VENUE', 'CATERING_SERVICE', "
    "'TRAVEL_AGENCY')"
)


def upgrade() -> None:
    op.drop_constraint(
        _STATUS_CONSTRAINT, "business_profile", schema="profiles", type_="check"
    )  # approved-destructive: immediately re-added below with a widened (not narrowed) value list
    op.create_check_constraint(
        _STATUS_CONSTRAINT,
        "business_profile",
        f"status IN {_STATUS_NEW_VALUES}",
        schema="profiles",
    )
    op.drop_constraint(
        _MAIN_CATEGORY_CONSTRAINT, "business_profile", schema="profiles", type_="check"
    )  # approved-destructive: immediately re-added below with a widened (not narrowed) value list
    op.create_check_constraint(
        _MAIN_CATEGORY_CONSTRAINT,
        "business_profile",
        f"main_category IS NULL OR main_category IN {_MAIN_CATEGORY_NEW_VALUES}",
        schema="profiles",
    )
    op.drop_constraint(
        _SUB_CATEGORY_CONSTRAINT, "business_profile", schema="profiles", type_="check"
    )  # approved-destructive: immediately re-added below with a widened (not narrowed) value list
    op.create_check_constraint(
        _SUB_CATEGORY_CONSTRAINT,
        "business_profile",
        f"sub_category IS NULL OR sub_category IN {_SUB_CATEGORY_NEW_VALUES}",
        schema="profiles",
    )
    op.add_column(
        "business_profile",
        sa.Column(
            "finance_offer_details_localized",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema="profiles",
    )
    op.add_column(
        "business_profile",
        sa.Column("promo_video_youtube_url", sa.Text(), nullable=True),
        schema="profiles",
    )


def downgrade() -> None:
    op.drop_column(
        "business_profile", "promo_video_youtube_url", schema="profiles"
    )  # approved-destructive: additive nullable column from this same migration's own upgrade()
    op.drop_column(
        "business_profile", "finance_offer_details_localized", schema="profiles"
    )  # approved-destructive: additive nullable column from this same migration's own upgrade()
    op.drop_constraint(
        _SUB_CATEGORY_CONSTRAINT, "business_profile", schema="profiles", type_="check"
    )  # approved-destructive: fails if any row already uses one of the 20 new sub-categories
    op.create_check_constraint(
        _SUB_CATEGORY_CONSTRAINT,
        "business_profile",
        f"sub_category IS NULL OR sub_category IN {_SUB_CATEGORY_OLD_VALUES}",
        schema="profiles",
    )
    op.drop_constraint(
        _MAIN_CATEGORY_CONSTRAINT, "business_profile", schema="profiles", type_="check"
    )  # approved-destructive: fails if any row already uses one of the 4 new main categories
    op.create_check_constraint(
        _MAIN_CATEGORY_CONSTRAINT,
        "business_profile",
        f"main_category IS NULL OR main_category IN {_MAIN_CATEGORY_OLD_VALUES}",
        schema="profiles",
    )
    op.drop_constraint(
        _STATUS_CONSTRAINT, "business_profile", schema="profiles", type_="check"
    )  # approved-destructive: fails if any row already uses PENDING_REVIEW/REJECTED
    op.create_check_constraint(
        _STATUS_CONSTRAINT,
        "business_profile",
        f"status IN {_STATUS_OLD_VALUES}",
        schema="profiles",
    )
