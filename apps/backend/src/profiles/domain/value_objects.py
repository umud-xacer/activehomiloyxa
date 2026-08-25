"""profiles -- value objects (DDD Sec 5.2 BC-02). Persistence-ignorant, mirrors
`catalog.domain.value_objects`'s style.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ProfileType(StrEnum):
    """DDD Sec 5.2 VO `ProfileType [P]` -- the closed set of the eight approved business-profile
    types (SRS Sec 4). See `docs/adr/0002-business-profile-type-vocabulary-correction.md`: the
    OpenAPI spec originally enumerated a different, real-estate-flavored eight-value set that
    conflicted with SRS Sec 4/DDD Sec 5.2; that ADR corrected `contracts/openapi.yaml` (and this
    module's own `interfaces/dto.py`/`ports.py` stubs) to the vocabulary below, which is the one
    this enum matches."""

    CONSTRUCTION_COMPANY = "CONSTRUCTION_COMPANY"
    MANUFACTURER = "MANUFACTURER"
    BUILDER = "BUILDER"
    SUPPLIER = "SUPPLIER"
    CONTRACTOR = "CONTRACTOR"
    ARCHITECT = "ARCHITECT"
    INTERIOR_DESIGNER = "INTERIOR_DESIGNER"
    SERVICE_PROVIDER = "SERVICE_PROVIDER"


class MainCategory(StrEnum):
    """Additive (Organizations Main-Category task, site-owner spec): a coarser, sector-facing
    grouping distinct from `ProfileType` — `ProfileType` stays the frozen SRS Sec 4 vocabulary
    (never touched here); this is a second, independent classification used only for the public
    `/companies` directory's category tabs and the mandatory onboarding-wizard selector. Two of
    the six original sectors (finance/mortgage, real-estate agencies) have no corresponding
    `ProfileType` at all, which is why this could not simply be derived from that enum.

    Widened 6→10 (ADR-0012, B2B Directory professional-upgrade task, site-owner spec): the last
    four values below (`TRANSPORT_LOGISTICS`, `LEGAL_CONSULTING_ACCOUNTING`,
    `HOME_APPLIANCES_EQUIPMENT`, `HOSPITALITY_SERVICES`) were added in the same widening as
    `ProfileStatus`'s new `PENDING_REVIEW`/`REJECTED` values -- see that ADR for the full
    rationale of extending this documented closed vocabulary."""

    FINANCE_MORTGAGE = "FINANCE_MORTGAGE"
    CONSTRUCTION_CONTRACTORS = "CONSTRUCTION_CONTRACTORS"
    MANUFACTURERS_MATERIALS = "MANUFACTURERS_MATERIALS"
    ARCHITECTURE_INTERIOR = "ARCHITECTURE_INTERIOR"
    REPAIR_SERVICES = "REPAIR_SERVICES"
    REAL_ESTATE_AGENCIES = "REAL_ESTATE_AGENCIES"
    TRANSPORT_LOGISTICS = "TRANSPORT_LOGISTICS"
    LEGAL_CONSULTING_ACCOUNTING = "LEGAL_CONSULTING_ACCOUNTING"
    HOME_APPLIANCES_EQUIPMENT = "HOME_APPLIANCES_EQUIPMENT"
    HOSPITALITY_SERVICES = "HOSPITALITY_SERVICES"


class SubCategory(StrEnum):
    """Additive (Organizations Sub-Category task, site-owner spec): a finer classification
    *within* one `MainCategory` (e.g. "Tijorat banki" vs. "Ipoteka markazi", both under
    `FINANCE_MORTGAGE`) -- used only for the public `/companies` directory's secondary filter
    dropdown. Always optional (unlike `main_category`, never required by onboarding): a profile
    with `main_category` set but `sub_category` still `None` simply shows no sub-category chip
    and matches every sub-category filter within its main category. `SUB_CATEGORIES_BY_MAIN_
    CATEGORY` below is the authoritative "which values are legal under which main category"
    mapping the domain layer validates against (`BusinessProfile.update_details`)."""

    # -- FINANCE_MORTGAGE ------------------------------------------------------------------------
    COMMERCIAL_BANK = "COMMERCIAL_BANK"
    MORTGAGE_CENTER = "MORTGAGE_CENTER"
    MICROFINANCE = "MICROFINANCE"
    INSURANCE = "INSURANCE"
    LEASING = "LEASING"
    # -- CONSTRUCTION_CONTRACTORS -----------------------------------------------------------------
    GENERAL_CONTRACTOR = "GENERAL_CONTRACTOR"
    SUBCONTRACTOR = "SUBCONTRACTOR"
    CIVIL_ENGINEERING = "CIVIL_ENGINEERING"
    RENOVATION_CONTRACTOR = "RENOVATION_CONTRACTOR"
    INFRASTRUCTURE_CONSTRUCTION = "INFRASTRUCTURE_CONSTRUCTION"
    # -- MANUFACTURERS_MATERIALS ------------------------------------------------------------------
    BUILDING_MATERIALS_MANUFACTURER = "BUILDING_MATERIALS_MANUFACTURER"
    FURNITURE_MANUFACTURER = "FURNITURE_MANUFACTURER"
    METAL_PRODUCTS_MANUFACTURER = "METAL_PRODUCTS_MANUFACTURER"
    CONCRETE_CEMENT_MANUFACTURER = "CONCRETE_CEMENT_MANUFACTURER"
    GLASS_ALUMINUM_MANUFACTURER = "GLASS_ALUMINUM_MANUFACTURER"
    # -- ARCHITECTURE_INTERIOR --------------------------------------------------------------------
    ARCHITECTURE_STUDIO = "ARCHITECTURE_STUDIO"
    INTERIOR_DESIGN_STUDIO = "INTERIOR_DESIGN_STUDIO"
    LANDSCAPE_DESIGN_STUDIO = "LANDSCAPE_DESIGN_STUDIO"
    ENGINEERING_DESIGN_STUDIO = "ENGINEERING_DESIGN_STUDIO"
    # -- REPAIR_SERVICES ---------------------------------------------------------------------------
    HOME_REPAIR_SERVICE = "HOME_REPAIR_SERVICE"
    PLUMBING_ELECTRICAL_SERVICE = "PLUMBING_ELECTRICAL_SERVICE"
    CLEANING_SERVICE = "CLEANING_SERVICE"
    APPLIANCE_REPAIR_SERVICE = "APPLIANCE_REPAIR_SERVICE"
    # -- REAL_ESTATE_AGENCIES ----------------------------------------------------------------------
    RESIDENTIAL_AGENCY = "RESIDENTIAL_AGENCY"
    COMMERCIAL_AGENCY = "COMMERCIAL_AGENCY"
    PROPERTY_MANAGEMENT = "PROPERTY_MANAGEMENT"
    VALUATION_SERVICE = "VALUATION_SERVICE"
    # -- TRANSPORT_LOGISTICS (ADR-0012) ------------------------------------------------------------
    FREIGHT_TRANSPORT = "FREIGHT_TRANSPORT"
    COURIER_DELIVERY = "COURIER_DELIVERY"
    CAR_RENTAL = "CAR_RENTAL"
    LOGISTICS_WAREHOUSING = "LOGISTICS_WAREHOUSING"
    MOVING_SERVICES = "MOVING_SERVICES"
    # -- LEGAL_CONSULTING_ACCOUNTING (ADR-0012) ------------------------------------------------------
    LAW_FIRM = "LAW_FIRM"
    ACCOUNTING_FIRM = "ACCOUNTING_FIRM"
    BUSINESS_CONSULTING = "BUSINESS_CONSULTING"
    TAX_ADVISORY = "TAX_ADVISORY"
    NOTARY_SERVICES = "NOTARY_SERVICES"
    # -- HOME_APPLIANCES_EQUIPMENT (ADR-0012) --------------------------------------------------------
    HOME_APPLIANCE_STORE = "HOME_APPLIANCE_STORE"
    ELECTRONICS_RETAILER = "ELECTRONICS_RETAILER"
    APPLIANCE_SERVICE_CENTER = "APPLIANCE_SERVICE_CENTER"
    EQUIPMENT_RENTAL = "EQUIPMENT_RENTAL"
    HVAC_EQUIPMENT_SUPPLIER = "HVAC_EQUIPMENT_SUPPLIER"
    # -- HOSPITALITY_SERVICES (ADR-0012) -------------------------------------------------------------
    HOTEL_OPERATOR = "HOTEL_OPERATOR"
    GUESTHOUSE_OPERATOR = "GUESTHOUSE_OPERATOR"
    EVENT_VENUE = "EVENT_VENUE"
    CATERING_SERVICE = "CATERING_SERVICE"
    TRAVEL_AGENCY = "TRAVEL_AGENCY"


SUB_CATEGORIES_BY_MAIN_CATEGORY: dict[MainCategory, tuple[SubCategory, ...]] = {
    MainCategory.FINANCE_MORTGAGE: (
        SubCategory.COMMERCIAL_BANK,
        SubCategory.MORTGAGE_CENTER,
        SubCategory.MICROFINANCE,
        SubCategory.INSURANCE,
        SubCategory.LEASING,
    ),
    MainCategory.CONSTRUCTION_CONTRACTORS: (
        SubCategory.GENERAL_CONTRACTOR,
        SubCategory.SUBCONTRACTOR,
        SubCategory.CIVIL_ENGINEERING,
        SubCategory.RENOVATION_CONTRACTOR,
        SubCategory.INFRASTRUCTURE_CONSTRUCTION,
    ),
    MainCategory.MANUFACTURERS_MATERIALS: (
        SubCategory.BUILDING_MATERIALS_MANUFACTURER,
        SubCategory.FURNITURE_MANUFACTURER,
        SubCategory.METAL_PRODUCTS_MANUFACTURER,
        SubCategory.CONCRETE_CEMENT_MANUFACTURER,
        SubCategory.GLASS_ALUMINUM_MANUFACTURER,
    ),
    MainCategory.ARCHITECTURE_INTERIOR: (
        SubCategory.ARCHITECTURE_STUDIO,
        SubCategory.INTERIOR_DESIGN_STUDIO,
        SubCategory.LANDSCAPE_DESIGN_STUDIO,
        SubCategory.ENGINEERING_DESIGN_STUDIO,
    ),
    MainCategory.REPAIR_SERVICES: (
        SubCategory.HOME_REPAIR_SERVICE,
        SubCategory.PLUMBING_ELECTRICAL_SERVICE,
        SubCategory.CLEANING_SERVICE,
        SubCategory.APPLIANCE_REPAIR_SERVICE,
    ),
    MainCategory.REAL_ESTATE_AGENCIES: (
        SubCategory.RESIDENTIAL_AGENCY,
        SubCategory.COMMERCIAL_AGENCY,
        SubCategory.PROPERTY_MANAGEMENT,
        SubCategory.VALUATION_SERVICE,
    ),
    MainCategory.TRANSPORT_LOGISTICS: (
        SubCategory.FREIGHT_TRANSPORT,
        SubCategory.COURIER_DELIVERY,
        SubCategory.CAR_RENTAL,
        SubCategory.LOGISTICS_WAREHOUSING,
        SubCategory.MOVING_SERVICES,
    ),
    MainCategory.LEGAL_CONSULTING_ACCOUNTING: (
        SubCategory.LAW_FIRM,
        SubCategory.ACCOUNTING_FIRM,
        SubCategory.BUSINESS_CONSULTING,
        SubCategory.TAX_ADVISORY,
        SubCategory.NOTARY_SERVICES,
    ),
    MainCategory.HOME_APPLIANCES_EQUIPMENT: (
        SubCategory.HOME_APPLIANCE_STORE,
        SubCategory.ELECTRONICS_RETAILER,
        SubCategory.APPLIANCE_SERVICE_CENTER,
        SubCategory.EQUIPMENT_RENTAL,
        SubCategory.HVAC_EQUIPMENT_SUPPLIER,
    ),
    MainCategory.HOSPITALITY_SERVICES: (
        SubCategory.HOTEL_OPERATOR,
        SubCategory.GUESTHOUSE_OPERATOR,
        SubCategory.EVENT_VENUE,
        SubCategory.CATERING_SERVICE,
        SubCategory.TRAVEL_AGENCY,
    ),
}


class ProfileStatus(StrEnum):
    """Physical DB `profiles.business_profile.status` CHECK. Originally a momentary
    `Created -> Active -> Archived` machine (Database Architecture Sec "profiles schema": "owner
    closure/suspension follow-through") where `application.ProfileUseCases.create_profile`
    immediately composed `.activate()` in the same request -- no admin sign-off existed at all.

    Widened (ADR-0012, B2B Directory professional-upgrade task, site-owner spec: "yangi
    tashkilotlar avtomatik PENDING_REVIEW statusini olsin"): `create_profile` now composes
    `.submit_for_review()` instead of `.activate()`, so every new company starts `PENDING_REVIEW`
    and stays invisible on the public directory/landing page (`ProfileUseCases.
    get_public_profile_by_slug`/`list_public_profiles`) until a reviewer decides it via the new
    `decide_registration` use case. `CREATED -> PENDING_REVIEW -> ACTIVE -> ARCHIVED` is the
    approval path; `PENDING_REVIEW -> REJECTED` the rejection path. `REJECTED` is not terminal --
    `BusinessProfile.update_details` on a `REJECTED` profile transitions it back to
    `PENDING_REVIEW` automatically (edit-to-resubmit), so an owner never needs a second, dedicated
    "resubmit" call."""

    CREATED = "CREATED"
    PENDING_REVIEW = "PENDING_REVIEW"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class BadgeStatus(StrEnum):
    """Physical DB `profiles.business_profile.badge_status` CHECK; `NULL` (never verified) is
    represented as `BusinessProfile.badge is None`, not a fourth enum member (`ck_badge_shape`:
    "(badge_status IS NULL) = (badge_issued_at IS NULL)")."""

    VALID = "VALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class CaseStatus(StrEnum):
    """Physical DB `profiles.verification_case.status` CHECK -- `Requested -> InReview ->
    Approved | Rejected`; the latter two are terminal (DDD Sec 5.2 VO `CaseStatus`)."""

    REQUESTED = "REQUESTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


TERMINAL_CASE_STATUSES = frozenset({CaseStatus.APPROVED, CaseStatus.REJECTED})


@dataclass(frozen=True)
class VerifiedBadge:
    """DDD Sec 5.2 VO `VerifiedBadge` (issue date, validity period, status). Constructed only by
    `BusinessProfile`'s own guarded transition methods -- never directly by application code
    (I-13's structural guard lives on `issue_badge`, see `verification_case.
    ApprovedVerificationProof`)."""

    status: BadgeStatus
    issued_at: datetime
    valid_until: datetime


@dataclass(frozen=True)
class Decision:
    """DDD Sec 5.2 VO `Decision` (outcome, reason, reviewer id, timestamp -- FR-PROF-005)."""

    outcome: CaseStatus
    """`APPROVED` or `REJECTED` only -- never `REQUESTED`/`IN_REVIEW` (enforced by
    `VerificationCase.decide`'s own parameter type, not re-checked here)."""
    reason: str | None
    reviewer_user_id: UUID
    decided_at: datetime
