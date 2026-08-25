"""profiles -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
operations tagged to this module (contracts/openapi.yaml). Schema only: no aggregate
type is exposed here, no business behaviour, no validation beyond what Pydantic
itself does structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from active_home_shared import CamelModel
from shared_kernel import LocalizedText


class PageInfo(CamelModel):
    """Cursor pagination metadata (OpenAPI `CursorPage.page`)."""

    limit: int
    next_cursor: str | None = None
    """Pass as `cursor` to fetch the next page; null when exhausted."""
    total: int | None = None
    """Present only where cheap to compute; may be null."""


class PortfolioItem(CamelModel):
    """OpenAPI `PortfolioItem`."""

    id: UUID
    media_asset_id: UUID
    position: int
    caption: LocalizedText | None = None


class TeamMember(CamelModel):
    """A user granted a role on a business profile (realised as an identity RoleAssignment scoped
    to the profile; the profile owner manages membership). No new aggregate is introduced."""

    user_id: UUID
    display_name: str | None = None
    role_code: str
    """A configured role code."""
    invited_at: datetime | None = None


MainCategoryLiteral = Literal[
    "FINANCE_MORTGAGE",
    "CONSTRUCTION_CONTRACTORS",
    "MANUFACTURERS_MATERIALS",
    "ARCHITECTURE_INTERIOR",
    "REPAIR_SERVICES",
    "REAL_ESTATE_AGENCIES",
    "TRANSPORT_LOGISTICS",
    "LEGAL_CONSULTING_ACCOUNTING",
    "HOME_APPLIANCES_EQUIPMENT",
    "HOSPITALITY_SERVICES",
]
"""Additive (Organizations Main-Category task, widened 6→10 by ADR-0012) -- a second, independent
sector classification alongside the frozen `profileType` vocabulary (see `profiles.domain.
MainCategory`'s own docstring for why it could not simply be derived from that enum)."""

SubCategoryLiteral = Literal[
    "COMMERCIAL_BANK",
    "MORTGAGE_CENTER",
    "MICROFINANCE",
    "INSURANCE",
    "LEASING",
    "GENERAL_CONTRACTOR",
    "SUBCONTRACTOR",
    "CIVIL_ENGINEERING",
    "RENOVATION_CONTRACTOR",
    "INFRASTRUCTURE_CONSTRUCTION",
    "BUILDING_MATERIALS_MANUFACTURER",
    "FURNITURE_MANUFACTURER",
    "METAL_PRODUCTS_MANUFACTURER",
    "CONCRETE_CEMENT_MANUFACTURER",
    "GLASS_ALUMINUM_MANUFACTURER",
    "ARCHITECTURE_STUDIO",
    "INTERIOR_DESIGN_STUDIO",
    "LANDSCAPE_DESIGN_STUDIO",
    "ENGINEERING_DESIGN_STUDIO",
    "HOME_REPAIR_SERVICE",
    "PLUMBING_ELECTRICAL_SERVICE",
    "CLEANING_SERVICE",
    "APPLIANCE_REPAIR_SERVICE",
    "RESIDENTIAL_AGENCY",
    "COMMERCIAL_AGENCY",
    "PROPERTY_MANAGEMENT",
    "VALUATION_SERVICE",
    "FREIGHT_TRANSPORT",
    "COURIER_DELIVERY",
    "CAR_RENTAL",
    "LOGISTICS_WAREHOUSING",
    "MOVING_SERVICES",
    "LAW_FIRM",
    "ACCOUNTING_FIRM",
    "BUSINESS_CONSULTING",
    "TAX_ADVISORY",
    "NOTARY_SERVICES",
    "HOME_APPLIANCE_STORE",
    "ELECTRONICS_RETAILER",
    "APPLIANCE_SERVICE_CENTER",
    "EQUIPMENT_RENTAL",
    "HVAC_EQUIPMENT_SUPPLIER",
    "HOTEL_OPERATOR",
    "GUESTHOUSE_OPERATOR",
    "EVENT_VENUE",
    "CATERING_SERVICE",
    "TRAVEL_AGENCY",
]
"""Additive (Organizations Sub-Category task, widened by ADR-0012's four new sectors) -- a finer
classification within one `MainCategoryLiteral` value; see `profiles.domain.
SUB_CATEGORIES_BY_MAIN_CATEGORY` for which codes are legal under which main category (enforced at
the domain layer, not by this Literal)."""


class BusinessProfileCreateRequest(CamelModel):
    """OpenAPI `BusinessProfileCreateRequest`."""

    profile_type: Literal[
        "CONSTRUCTION_COMPANY",
        "MANUFACTURER",
        "BUILDER",
        "SUPPLIER",
        "CONTRACTOR",
        "ARCHITECT",
        "INTERIOR_DESIGNER",
        "SERVICE_PROVIDER",
    ]
    name: LocalizedText
    description: LocalizedText | None = None
    contacts: dict[str, Any] | None = None
    address: str | None = None
    main_category: MainCategoryLiteral | None = None
    sub_category: SubCategoryLiteral | None = None


class BusinessProfile(CamelModel):
    """A company presence of one of the eight closed profile types (BC-02)."""

    id: UUID
    owner_user_id: UUID
    profile_type: Literal[
        "CONSTRUCTION_COMPANY",
        "MANUFACTURER",
        "BUILDER",
        "SUPPLIER",
        "CONTRACTOR",
        "ARCHITECT",
        "INTERIOR_DESIGNER",
        "SERVICE_PROVIDER",
    ]
    """Closed platform vocabulary (eight types)."""
    name: LocalizedText
    description: LocalizedText | None = None
    contacts: dict[str, Any] | None = None
    """Phones/emails/site (CompanyDetails)."""
    address: str | None = None
    slug: str
    """Display-only routing; not an identity."""
    status: Literal["CREATED", "PENDING_REVIEW", "ACTIVE", "REJECTED", "ARCHIVED"]
    """ADR-0012: `PENDING_REVIEW` (default for a new profile, awaiting reviewer decision) and
    `REJECTED` (editing the profile resubmits it to `PENDING_REVIEW`) widen the original
    `CREATED`/`ACTIVE`/`ARCHIVED` set."""
    badge: BusinessProfileBadge | None = None
    """Trust badge sub-state (null = never verified)."""
    logo_media_asset_id: UUID | None = None
    """A media asset reference, not a resolved URL -- mirrors `PortfolioItem.media_asset_id`'s
    own convention (`GET /media/{id}` resolves the CDN URL, the same indirection the owner-admin
    panel's category icon already uses)."""
    banner_media_asset_id: UUID | None = None
    subscription_status: Literal["ACTIVE", "EXPIRED", "NONE"] = "NONE"
    """Monetization: whether this profile currently holds a valid `ACTIVE_SUBSCRIPTION`
    entitlement. Individuals' own profiles (if any) are always `NONE` and irrelevant -- this only
    gates a `LEGAL_ENTITY`-owned profile's public visibility (see `listPublicBusinessProfiles`'s
    own docstring)."""
    subscription_valid_until: datetime | None = None
    onboarding_completed_at: datetime | None = None
    """ADR-0010. `null` = the owner has not yet finished the mandatory setup wizard --
    `requireOnboardedLegalEntity` on the frontend redirects there until this is set."""
    trial_starts_at: datetime | None = None
    trial_ends_at: datetime | None = None
    """ADR-0010. Display-only ("N kun qoldi"); `subscription_status` above is the actual
    entitlement read, not a comparison against this field."""
    promo_video_media_asset_ids: list[UUID] = Field(default_factory=list)
    """Additive (landing-page promo-video business rule): up to 2 media asset references, each
    resolved to a CDN url the same way `logo_media_asset_id`/`PortfolioItem.media_asset_id` are
    -- via `GET /media/{id}`, never a resolved URL inline here."""
    main_category: MainCategoryLiteral | None = None
    """Additive (Organizations Main-Category task): the sector tab this profile appears under on
    the public /companies directory. Null on profiles that pre-date this field."""
    sub_category: SubCategoryLiteral | None = None
    """Additive (Organizations Sub-Category task): a finer classification within `main_category`.
    Null on profiles that have not set one -- always optional, unlike `main_category`."""
    finance_offer_details: LocalizedText | None = None
    """Additive (ADR-0012, "Bank/Finans bloki"): free-text ipoteka/kredit terms, only meaningful
    (and only rendered by the frontend) when `main_category == "FINANCE_MORTGAGE"`."""
    promo_video_youtube_url: str | None = None
    """Additive (ADR-0012): an external YouTube link, alongside the existing uploaded
    `promo_video_media_asset_ids` -- host-validated server-side (youtube.com/youtu.be only)."""
    created_at: datetime


class PromoVideoAddRequest(CamelModel):
    """Additive (landing-page promo-video business rule). `POST /business-profiles/{id}/
    promo-videos` body -- just the already-uploaded media asset id, mirroring `updateBusinessProfileBranding`'s
    shape rather than `PortfolioItem`'s (no position/caption for promo videos)."""

    media_asset_id: UUID


class BusinessProfileBadge(CamelModel):
    """Trust badge sub-state (null = never verified)."""

    status: Literal["VALID", "EXPIRED", "REVOKED"] | None = None
    issued_at: datetime | None = None
    valid_until: datetime | None = None


class VerificationDecisionRequest(CamelModel):
    """OpenAPI `VerificationDecisionRequest`."""

    outcome: Literal["APPROVED", "REJECTED"]
    reason: str | None = None


class VerificationCase(CamelModel):
    """A paid, manual verification work item (BC-02)."""

    id: UUID
    business_profile_id: UUID
    entitlement_id: UUID | None = None
    """VerificationEligibility precondition (I-12)."""
    status: Literal["REQUESTED", "IN_REVIEW", "APPROVED", "REJECTED"]
    sla_due_at: datetime
    documents: list[SubmittedDocument] | None = None
    decision: VerificationCaseDecision | None = None
    created_at: datetime


class SubmittedDocument(CamelModel):
    """OpenAPI `SubmittedDocument`."""

    id: UUID | None = None
    media_asset_id: UUID
    """Image asset (images only, FR-PROF-003)."""
    document_kind: str
    position: int | None = None


class VerificationCaseDecision(CamelModel):
    """OpenAPI `VerificationCaseDecision`."""

    outcome: Literal["APPROVED", "REJECTED"] | None = None
    reason: str | None = None
    decided_at: datetime | None = None


class BusinessProfilePage(CamelModel):
    """A cursor-paginated page of `BusinessProfile` (OpenAPI `CursorPage` composed with
    `items: BusinessProfile[]` via `allOf`)."""

    items: list[BusinessProfile]
    page: PageInfo


class VerificationCasePage(CamelModel):
    """A cursor-paginated page of `VerificationCase` (OpenAPI `CursorPage` composed with
    `items: VerificationCase[]` via `allOf`)."""

    items: list[VerificationCase]
    page: PageInfo


class VerificationRequestCreate(CamelModel):
    """OpenAPI `VerificationRequestCreate`."""

    entitlement_id: UUID
    documents: list[SubmittedDocument]


class BusinessProfileUpdateRequest(CamelModel):
    """Partial update; profileType is immutable and cannot be changed."""

    name: LocalizedText | None = None
    description: LocalizedText | None = None
    contacts: dict[str, Any] | None = None
    address: str | None = None
    main_category: MainCategoryLiteral | None = None
    sub_category: SubCategoryLiteral | None = None


class BusinessProfileBrandingRequest(CamelModel):
    """Monetization/Landing-Page task: sets the logo/banner in one call, both applied verbatim
    (`null` clears that one) -- mirrors `BusinessProfile.update_branding`'s own docstring."""

    logo_media_asset_id: UUID | None = None
    banner_media_asset_id: UUID | None = None


class BusinessProfileLandingExtrasRequest(CamelModel):
    """ADR-0012: the finance-terms block and YouTube promo link, applied verbatim (`null` clears
    that one) -- mirrors `BusinessProfileBrandingRequest`'s own shape."""

    finance_offer_details: LocalizedText | None = None
    promo_video_youtube_url: str | None = None


class BusinessProfileRegistrationDecisionRequest(CamelModel):
    """ADR-0012: `POST /admin/business-profiles/{profileId}/decision` body -- same shape as
    `VerificationDecisionRequest`, kept as a distinct class since the two decide unrelated
    aggregates (a `BusinessProfile`'s own registration status vs. a separate `VerificationCase`).
    Named distinctly from identity's own `RegistrationDecisionRequest` (ADR-0007, account
    registration review) -- unrelated feature, same shape, different aggregate; a shared OpenAPI
    schema name would collide."""

    outcome: Literal["APPROVED", "REJECTED"]
    reason: str | None = None
