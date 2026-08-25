"""SQLAlchemy models for profiles' Postgres-backed `BusinessProfile`/`VerificationCase`
aggregates (Physical DB "profiles schema" section). `PortfolioItemRow`/`SubmittedDocumentRow` are
child entities (DDD Sec 5.2, `ON DELETE CASCADE` per the physical spec) with no repository of
their own -- persisted as part of their aggregate's own repository unit of work, mirroring
`catalog.infrastructure.persistence.models`'s `ImageAttachmentRow` pattern.
`VerificationEntitlementProjectionRow` is not an aggregate -- a locally projected read model
(I-12), keyed by `entitlement_id` (not in the documented Physical Database Design; a
locally-necessary addition, the same precedent `catalog.infrastructure.persistence.models.
SubscriptionProjectionRow` set for I-08 -- see `profiles.application.ports.
VerificationEligibilitySnapshot`'s own docstring for why it is keyed this way).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backbone.idempotency import make_processed_event_model
from backbone.outbox import make_outbox_event_model
from backbone.persistence import AggregateMixin, uuid7
from profiles.infrastructure.persistence.base import ProfilesBase

_PROFILE_TYPES = (
    "('CONSTRUCTION_COMPANY', 'MANUFACTURER', 'BUILDER', 'SUPPLIER', 'CONTRACTOR', 'ARCHITECT', "
    "'INTERIOR_DESIGNER', 'SERVICE_PROVIDER')"
)
_MAIN_CATEGORIES = (
    "('FINANCE_MORTGAGE', 'CONSTRUCTION_CONTRACTORS', 'MANUFACTURERS_MATERIALS', "
    "'ARCHITECTURE_INTERIOR', 'REPAIR_SERVICES', 'REAL_ESTATE_AGENCIES', "
    "'TRANSPORT_LOGISTICS', 'LEGAL_CONSULTING_ACCOUNTING', 'HOME_APPLIANCES_EQUIPMENT', "
    "'HOSPITALITY_SERVICES')"
)
"""Widened 6→10 by ADR-0012 (B2B Directory professional-upgrade task) -- the last four values are
new."""
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
    "'RESIDENTIAL_AGENCY', 'COMMERCIAL_AGENCY', 'PROPERTY_MANAGEMENT', 'VALUATION_SERVICE', "
    "'FREIGHT_TRANSPORT', 'COURIER_DELIVERY', 'CAR_RENTAL', 'LOGISTICS_WAREHOUSING', "
    "'MOVING_SERVICES', "
    "'LAW_FIRM', 'ACCOUNTING_FIRM', 'BUSINESS_CONSULTING', 'TAX_ADVISORY', 'NOTARY_SERVICES', "
    "'HOME_APPLIANCE_STORE', 'ELECTRONICS_RETAILER', 'APPLIANCE_SERVICE_CENTER', "
    "'EQUIPMENT_RENTAL', 'HVAC_EQUIPMENT_SUPPLIER', "
    "'HOTEL_OPERATOR', 'GUESTHOUSE_OPERATOR', 'EVENT_VENUE', 'CATERING_SERVICE', "
    "'TRAVEL_AGENCY')"
)
"""Widened by ADR-0012's four new sectors (20 new sub-categories)."""
_PROFILE_STATUSES = "('CREATED', 'PENDING_REVIEW', 'ACTIVE', 'REJECTED', 'ARCHIVED')"
"""Widened by ADR-0012 -- see `profiles.domain.value_objects.ProfileStatus`'s own docstring."""
_BADGE_STATUSES = "('VALID', 'EXPIRED', 'REVOKED')"
_CASE_STATUSES = "('REQUESTED', 'IN_REVIEW', 'APPROVED', 'REJECTED')"
_DECISION_OUTCOMES = "('APPROVED', 'REJECTED')"
_ELIGIBILITY_STATES = "('ACTIVE', 'EXPIRED', 'REVOKED')"


class BusinessProfileRow(ProfilesBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "business_profile"

    owner_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_type: Mapped[str] = mapped_column(Text, nullable=False)
    name_localized: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description_localized: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    contacts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="ACTIVE")
    badge_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    badge_issued_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    badge_valid_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    logo_media_asset_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    banner_media_asset_id: Mapped[PyUUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    trial_starts_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    promo_video_media_asset_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    """Additive (landing-page promo-video business rule): a small (<=2), ordered JSON array of
    media asset id strings -- no position/caption semantics needed, so a dedicated child table
    (`portfolio_item`'s pattern) would be pure overhead for this bounded collection."""
    main_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Additive (Organizations Main-Category task). Nullable at the DB level (existing rows
    predate this field and are never backfilled) even though the onboarding wizard treats it as
    mandatory going forward -- that mandate is enforced in the domain layer
    (`BusinessProfile.complete_onboarding`), the same "DB permissive, aggregate strict" split
    `onboarding_completed_at`'s own sibling fields already use."""
    sub_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Additive (Organizations Sub-Category task). Nullable and stays nullable -- unlike
    `main_category`, never required by onboarding. The cross-field "this code belongs to that
    main_category" rule is a domain-layer invariant, not expressed by this column's own CHECK
    (a flat membership check only, mirroring `ck_business_profile_main_category`'s own shape)."""
    finance_offer_details_localized: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Additive (ADR-0012, "Bank/Finans bloki"): free-text ipoteka/kredit terms, only ever
    rendered by the frontend when `main_category == 'FINANCE_MORTGAGE'` -- no CHECK enforces
    that restriction at the DB level, same "domain/interfaces decide, column stays permissive"
    split `main_category`'s own sibling fields already use."""
    promo_video_youtube_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Additive (ADR-0012): host-validated (youtube.com/youtu.be) by the application layer, not
    by a column CHECK -- mirrors this table's existing "validation lives one layer up" fields."""

    __table_args__ = (
        CheckConstraint(f"profile_type IN {_PROFILE_TYPES}", name="ck_business_profile_type"),
        CheckConstraint(
            f"main_category IS NULL OR main_category IN {_MAIN_CATEGORIES}",
            name="ck_business_profile_main_category",
        ),
        CheckConstraint(
            f"sub_category IS NULL OR sub_category IN {_SUB_CATEGORIES}",
            name="ck_business_profile_sub_category",
        ),
        CheckConstraint(f"status IN {_PROFILE_STATUSES}", name="ck_business_profile_status"),
        CheckConstraint(
            f"badge_status IS NULL OR badge_status IN {_BADGE_STATUSES}",
            name="ck_business_profile_badge_status",
        ),
        CheckConstraint(
            "(badge_status IS NULL) = (badge_issued_at IS NULL)", name="ck_badge_shape"
        ),
        CheckConstraint(
            "(trial_starts_at IS NULL) = (trial_ends_at IS NULL)",
            name="ck_trial_shape",
        ),
        CheckConstraint(
            "onboarding_completed_at IS NULL OR trial_starts_at IS NOT NULL",
            name="ck_onboarding_implies_trial",
        ),
        CheckConstraint(
            "name_localized ? 'uz_latn' OR name_localized ? 'ru'",
            name="ck_profile_name_canonical",
        ),
        Index("ix_business_profile_owner_user_id", "owner_user_id"),
    )


class PortfolioItemRow(ProfilesBase):  # type: ignore[misc,valid-type]
    """Child entity of `BusinessProfile` (DDD Sec 5.2) -- no repository of its own."""

    __tablename__ = "portfolio_item"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    business_profile_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("profiles.business_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    media_asset_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    caption_localized: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("position BETWEEN 1 AND 50", name="ck_portfolio_item_position"),
        UniqueConstraint(
            "business_profile_id", "position", name="ux_portfolio_item_profile_position"
        ),
    )


class VerificationCaseRow(ProfilesBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "verification_case"

    business_profile_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("profiles.business_profile.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entitlement_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="REQUESTED")
    sla_due_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    decision_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_user_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {_CASE_STATUSES}", name="ck_verification_case_status"),
        CheckConstraint(
            f"decision_outcome IS NULL OR decision_outcome IN {_DECISION_OUTCOMES}",
            name="ck_verification_case_decision_outcome",
        ),
        CheckConstraint(
            "(status IN ('APPROVED','REJECTED')) = "
            "(decision_outcome IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_decision_shape",
        ),
        Index("ix_verification_case_business_profile_id", "business_profile_id"),
        Index("ix_verification_case_status", "status"),
    )


class SubmittedDocumentRow(ProfilesBase):  # type: ignore[misc,valid-type]
    """Child entity of `VerificationCase` (DDD Sec 5.2) -- no repository of its own."""

    __tablename__ = "submitted_document"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    verification_case_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("profiles.verification_case.id", ondelete="CASCADE"),
        nullable=False,
    )
    media_asset_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    document_kind: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "verification_case_id", "position", name="ux_submitted_document_case_position"
        ),
    )


class VerificationEntitlementProjectionRow(ProfilesBase):  # type: ignore[misc,valid-type]
    """A locally projected read model of a billing `VerificationEligibility` entitlement (I-12)
    -- not an aggregate (no `AggregateMixin`: this row is a cache, rebuilt idempotently from
    billing's own outbox events, never itself the source of truth). Keyed by `entitlement_id`
    (see module docstring)."""

    __tablename__ = "verification_entitlement_projection"

    entitlement_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    business_profile_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    activation_state: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"activation_state IN {_ELIGIBILITY_STATES}",
            name="ck_verification_entitlement_projection_state",
        ),
        Index(
            "ix_verification_entitlement_projection_profile",
            "business_profile_id",
            "activation_state",
            "valid_until",
        ),
    )


class SubscriptionEntitlementProjectionRow(ProfilesBase):  # type: ignore[misc,valid-type]
    """A locally projected read model of a billing `ACTIVE_SUBSCRIPTION` entitlement
    (Monetization task) -- not an aggregate, the same "cache, not source of truth" reasoning
    `VerificationEntitlementProjectionRow` above documents. Keyed by `business_profile_id`
    directly (see `profiles.application.ports.SubscriptionEligibilitySnapshot`'s own docstring for
    why this table's key differs from verification's own entitlement-keyed one)."""

    __tablename__ = "subscription_entitlement_projection"

    business_profile_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    entitlement_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    activation_state: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"activation_state IN {_ELIGIBILITY_STATES}",
            name="ck_subscription_entitlement_projection_state",
        ),
        Index(
            "ix_subscription_entitlement_projection_state",
            "activation_state",
            "valid_until",
        ),
    )


OutboxEventRow: Any = make_outbox_event_model(ProfilesBase)
ProcessedEventRow: Any = make_processed_event_model(ProfilesBase)
