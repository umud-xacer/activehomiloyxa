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
    the six sectors (finance/mortgage, real-estate agencies) have no corresponding `ProfileType`
    at all, which is why this could not simply be derived from that enum."""

    FINANCE_MORTGAGE = "FINANCE_MORTGAGE"
    CONSTRUCTION_CONTRACTORS = "CONSTRUCTION_CONTRACTORS"
    MANUFACTURERS_MATERIALS = "MANUFACTURERS_MATERIALS"
    ARCHITECTURE_INTERIOR = "ARCHITECTURE_INTERIOR"
    REPAIR_SERVICES = "REPAIR_SERVICES"
    REAL_ESTATE_AGENCIES = "REAL_ESTATE_AGENCIES"


class ProfileStatus(StrEnum):
    """Physical DB `profiles.business_profile.status` CHECK -- `Created -> Active -> Archived`
    (Database Architecture Sec "profiles schema": "owner closure/suspension follow-through").
    `CREATED` is a momentary, always-recorded first transition: `BusinessProfile.create()`
    produces it, and `application.ProfileUseCases.create_profile` immediately composes
    `.activate()` in the same request/transaction (no document describes a distinct manual
    activation step) -- the same "two recorded transitions, one request" composition
    `catalog.domain.listing.Listing.create`+`.publish()` uses for immediate publication."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
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
