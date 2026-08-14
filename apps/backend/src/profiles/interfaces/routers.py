"""FastAPI routers implementing exactly the 13 profiles-related OpenAPI operations P-11 builds
(`contracts/openapi.yaml`): 11 tagged `Business Profiles` and 2 tagged `Administration`
(`listVerificationQueue`, `decideVerification`) -- both admin operations act purely on profiles'
own aggregates (`VerificationCase`), so they are implemented here, mirroring `billing.interfaces.
routers`'s own precedent exactly (the OpenAPI tag is a documentation grouping, not a module-
ownership signal). Thin translation only: path/body -> use case call -> domain object -> already-
frozen `interfaces/dto.py` DTO. All business logic lives in `application`/`domain`; this module
owns none.

`listTeamMembers`/`addTeamMember`/`removeTeamMember` are deliberately NOT implemented here -- see
`profiles/README.md` "Known gaps": no approved document models a "team member" concept for BC-02
(DDD Sec 5.2's own `BusinessProfile` aggregate has no such entity), and identity's frozen
`interfaces/ports.py` exposes no port for assigning a role scoped to a profile that another module
could call. `interfaces/ports.py`'s `ProfileQueryPort` Protocol still declares these three methods
(frozen from Task P-01) but no router wires them to a real implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from profiles.application import ProfileUseCases, VerificationUseCases
from profiles.domain import BusinessProfile as BusinessProfileAggregate
from profiles.domain import CaseStatus, ProfileType
from profiles.domain import VerificationCase as VerificationCaseAggregate
from profiles.domain.portfolio_item import PortfolioItem as PortfolioItemEntity
from profiles.interfaces.auth import ActingProfileManager, ActingReviewer, ActingUser
from profiles.interfaces.di import (
    get_acting_profile_manager,
    get_acting_reviewer,
    get_acting_user,
    get_profile_use_cases,
    get_verification_use_cases,
)
from profiles.interfaces.dto import BusinessProfile as BusinessProfileDto
from profiles.interfaces.dto import BusinessProfileBadge as BusinessProfileBadgeDto
from profiles.interfaces.dto import (
    BusinessProfileBrandingRequest,
    BusinessProfileCreateRequest,
    BusinessProfilePage,
    BusinessProfileUpdateRequest,
    PageInfo,
    VerificationCasePage,
    VerificationDecisionRequest,
    VerificationRequestCreate,
)
from profiles.interfaces.dto import PortfolioItem as PortfolioItemDto
from profiles.interfaces.dto import SubmittedDocument as SubmittedDocumentDto
from profiles.interfaces.dto import VerificationCase as VerificationCaseDto
from profiles.interfaces.dto import VerificationCaseDecision as VerificationCaseDecisionDto
from shared_kernel import BusinessProfileId

profiles_router = APIRouter(tags=["Business Profiles"])
admin_profiles_router = APIRouter(tags=["Administration"])


def _clamp_limit(limit: int | None) -> int:
    return min(max(limit or 20, 1), 100)


def _to_portfolio_item_dto(item: PortfolioItemEntity) -> PortfolioItemDto:
    return PortfolioItemDto(
        id=item.id, media_asset_id=item.media_asset_id, position=item.position, caption=item.caption
    )


async def _to_profile_dto(
    profile: BusinessProfileAggregate, *, use_cases: ProfileUseCases
) -> BusinessProfileDto:
    badge = (
        BusinessProfileBadgeDto(
            status=profile.badge.status.value,
            issued_at=profile.badge.issued_at,
            valid_until=profile.badge.valid_until,
        )
        if profile.badge
        else None
    )
    subscription_status, subscription_valid_until = await use_cases.get_subscription_status(
        profile.id, now=datetime.now(UTC)
    )
    return BusinessProfileDto(
        id=profile.id.value,
        owner_user_id=profile.owner_user_id.value,
        profile_type=profile.profile_type.value,
        name=profile.name,
        description=profile.description,
        contacts=profile.contacts,
        address=profile.address,
        slug=profile.slug,
        status=profile.status.value,
        badge=badge,
        logo_media_asset_id=profile.logo_media_asset_id,
        banner_media_asset_id=profile.banner_media_asset_id,
        subscription_status=subscription_status,
        subscription_valid_until=subscription_valid_until,
        onboarding_completed_at=profile.onboarding_completed_at,
        trial_starts_at=profile.trial_starts_at,
        trial_ends_at=profile.trial_ends_at,
        created_at=profile.created_at,
    )


def _to_case_dto(case: VerificationCaseAggregate) -> VerificationCaseDto:
    decision = (
        VerificationCaseDecisionDto(
            # `Decision.outcome` is `CaseStatus`-typed (domain-wide vocabulary), but its own
            # docstring guarantees only APPROVED/REJECTED ever appear here (VerificationCase.
            # decide's own parameter never accepts REQUESTED/IN_REVIEW) -- narrowed for the DTO's
            # closed two-value Literal.
            outcome=cast(Literal["APPROVED", "REJECTED"], case.decision.outcome.value),
            reason=case.decision.reason,
            decided_at=case.decision.decided_at,
        )
        if case.decision
        else None
    )
    return VerificationCaseDto(
        id=case.id,
        business_profile_id=case.business_profile_id.value,
        entitlement_id=case.entitlement_id,
        status=case.status.value,
        sla_due_at=case.sla_due_at,
        documents=[
            SubmittedDocumentDto(
                id=document.id,
                media_asset_id=document.media_asset_id,
                document_kind=document.document_kind,
                position=document.position,
            )
            for document in case.documents
        ],
        decision=decision,
        created_at=case.created_at,
    )


# --- Business Profiles (public read surface) ------------------------------------------------


@profiles_router.get("/business-profiles", operation_id="listBusinessProfiles")
async def list_business_profiles(
    profileType: Literal[
        "CONSTRUCTION_COMPANY",
        "MANUFACTURER",
        "BUILDER",
        "SUPPLIER",
        "CONTRACTOR",
        "ARCHITECT",
        "INTERIOR_DESIGNER",
        "SERVICE_PROVIDER",
    ]
    | None = None,
    verifiedOnly: bool | None = None,
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> BusinessProfilePage:
    page_limit = _clamp_limit(limit)
    profiles, next_cursor = await use_cases.list_public_profiles(
        profile_type=ProfileType(profileType) if profileType else None,
        verified_only=bool(verifiedOnly),
        cursor=cursor,
        limit=page_limit,
    )
    return BusinessProfilePage(
        items=[await _to_profile_dto(profile, use_cases=use_cases) for profile in profiles],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


@profiles_router.post("/business-profiles", operation_id="createBusinessProfile", status_code=201)
async def create_business_profile(
    body: BusinessProfileCreateRequest,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> BusinessProfileDto:
    profile = await use_cases.create_profile(
        owner_user_id=user.account_id,
        profile_type=ProfileType(body.profile_type),
        name=body.name,
        description=body.description,
        contacts=body.contacts,
        address=body.address,
        now=datetime.now(UTC),
    )
    return await _to_profile_dto(profile, use_cases=use_cases)


@profiles_router.get("/business-profiles/{profileId}", operation_id="getBusinessProfile")
async def get_business_profile(
    profileId: UUID, use_cases: ProfileUseCases = Depends(get_profile_use_cases)
) -> BusinessProfileDto:
    profile = await use_cases.get_profile(BusinessProfileId(value=profileId))
    return await _to_profile_dto(profile, use_cases=use_cases)


@profiles_router.get("/business-profiles/slug/{slug}", operation_id="getBusinessProfileBySlug")
async def get_business_profile_by_slug(
    slug: str, use_cases: ProfileUseCases = Depends(get_profile_use_cases)
) -> BusinessProfileDto:
    """ADR-0010. The public landing-page read (`companies/$slug.tsx`) -- unlike
    `getBusinessProfile` above, 404s once the profile is no longer entitled (trial lapsed,
    subscription lapsed, never onboarded)."""
    profile = await use_cases.get_public_profile_by_slug(slug, now=datetime.now(UTC))
    return await _to_profile_dto(profile, use_cases=use_cases)


@profiles_router.post(
    "/business-profiles/{profileId}/complete-onboarding", operation_id="completeOnboarding"
)
async def complete_onboarding(
    profileId: UUID,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> BusinessProfileDto:
    """ADR-0010. Ends the mandatory onboarding wizard, starting the 5-day free trial. Raises
    `422 VALIDATION_FAILED` (`OnboardingIncompleteError`) if a mandatory field is still missing,
    `409 ILLEGAL_STATE_TRANSITION` if this profile already completed onboarding once."""
    profile = await use_cases.complete_onboarding(
        BusinessProfileId(value=profileId), owner_user_id=user.account_id, now=datetime.now(UTC)
    )
    return await _to_profile_dto(profile, use_cases=use_cases)


@profiles_router.patch("/business-profiles/{profileId}", operation_id="updateBusinessProfile")
async def update_business_profile(
    profileId: UUID,
    body: BusinessProfileUpdateRequest,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> BusinessProfileDto:
    profile = await use_cases.update_profile(
        BusinessProfileId(value=profileId),
        owner_user_id=user.account_id,
        name=body.name,
        description=body.description,
        contacts=body.contacts,
        address=body.address,
        now=datetime.now(UTC),
    )
    return await _to_profile_dto(profile, use_cases=use_cases)


@profiles_router.patch(
    "/business-profiles/{profileId}/branding", operation_id="updateBusinessProfileBranding"
)
async def update_business_profile_branding(
    profileId: UUID,
    body: BusinessProfileBrandingRequest,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> BusinessProfileDto:
    profile = await use_cases.update_branding(
        BusinessProfileId(value=profileId),
        owner_user_id=user.account_id,
        logo_media_asset_id=body.logo_media_asset_id,
        banner_media_asset_id=body.banner_media_asset_id,
        now=datetime.now(UTC),
    )
    return await _to_profile_dto(profile, use_cases=use_cases)


@profiles_router.delete(
    "/business-profiles/{profileId}", operation_id="archiveBusinessProfile", status_code=204
)
async def archive_business_profile(
    profileId: UUID,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> None:
    await use_cases.archive_profile(
        BusinessProfileId(value=profileId), owner_user_id=user.account_id, now=datetime.now(UTC)
    )


# --- Portfolio -----------------------------------------------------------------------------


@profiles_router.get("/business-profiles/{profileId}/portfolio", operation_id="listPortfolio")
async def list_portfolio(
    profileId: UUID, use_cases: ProfileUseCases = Depends(get_profile_use_cases)
) -> list[PortfolioItemDto]:
    items = await use_cases.list_portfolio(BusinessProfileId(value=profileId))
    return [_to_portfolio_item_dto(item) for item in items]


@profiles_router.post(
    "/business-profiles/{profileId}/portfolio", operation_id="addPortfolioItem", status_code=201
)
async def add_portfolio_item(
    profileId: UUID,
    body: PortfolioItemDto,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> PortfolioItemDto:
    profile = await use_cases.add_portfolio_item(
        BusinessProfileId(value=profileId),
        owner_user_id=user.account_id,
        media_asset_id=body.media_asset_id,
        caption=body.caption,
        now=datetime.now(UTC),
    )
    return _to_portfolio_item_dto(profile.portfolio[-1])


@profiles_router.delete(
    "/business-profiles/{profileId}/portfolio/{itemId}",
    operation_id="removePortfolioItem",
    status_code=204,
)
async def remove_portfolio_item(
    profileId: UUID,
    itemId: UUID,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> None:
    await use_cases.remove_portfolio_item(
        BusinessProfileId(value=profileId),
        itemId,
        owner_user_id=user.account_id,
        now=datetime.now(UTC),
    )


# --- Verification (owner-facing) ------------------------------------------------------------


@profiles_router.get(
    "/business-profiles/{profileId}/verification", operation_id="getVerificationCase"
)
async def get_verification_case(
    profileId: UUID,
    user: ActingUser = Depends(get_acting_user),
    use_cases: VerificationUseCases = Depends(get_verification_use_cases),
) -> VerificationCaseDto:
    case = await use_cases.get_current_case(
        BusinessProfileId(value=profileId), owner_user_id=user.account_id
    )
    return _to_case_dto(case)


@profiles_router.post(
    "/business-profiles/{profileId}/verification",
    operation_id="requestVerification",
    status_code=201,
)
async def request_verification(
    profileId: UUID,
    body: VerificationRequestCreate,
    user: ActingUser = Depends(get_acting_user),
    use_cases: VerificationUseCases = Depends(get_verification_use_cases),
) -> VerificationCaseDto:
    case = await use_cases.request_verification(
        BusinessProfileId(value=profileId),
        owner_user_id=user.account_id,
        entitlement_id=body.entitlement_id,
        documents=[
            (document.media_asset_id, document.document_kind) for document in body.documents
        ],
        now=datetime.now(UTC),
    )
    return _to_case_dto(case)


# --- Verification queue (reviewer-only, Administration tag) ---------------------------------


@admin_profiles_router.get("/admin/verification-queue", operation_id="listVerificationQueue")
async def list_verification_queue(
    status: Literal["REQUESTED", "IN_REVIEW", "APPROVED", "REJECTED"] | None = None,
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    _reviewer: ActingReviewer = Depends(get_acting_reviewer),
    use_cases: VerificationUseCases = Depends(get_verification_use_cases),
) -> VerificationCasePage:
    page_limit = _clamp_limit(limit)
    cases, next_cursor = await use_cases.list_queue(
        status=CaseStatus(status) if status else None, cursor=cursor, limit=page_limit
    )
    return VerificationCasePage(
        items=[_to_case_dto(case) for case in cases],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


@admin_profiles_router.post(
    "/admin/verification-queue/{caseId}/decision", operation_id="decideVerification"
)
async def decide_verification(
    caseId: UUID,
    body: VerificationDecisionRequest,
    reviewer: ActingReviewer = Depends(get_acting_reviewer),
    use_cases: VerificationUseCases = Depends(get_verification_use_cases),
) -> VerificationCaseDto:
    case = await use_cases.decide_verification(
        caseId,
        reviewer_user_id=reviewer.account_id.value,
        outcome=CaseStatus(body.outcome),
        reason=body.reason,
        now=datetime.now(UTC),
    )
    return _to_case_dto(case)


# --- Company management (owner-admin-panel-only, Administration tag) ------------------------


@admin_profiles_router.get("/admin/business-profiles", operation_id="adminListBusinessProfiles")
async def admin_list_business_profiles(
    status: Literal["CREATED", "ACTIVE", "ARCHIVED"] | None = None,
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    _manager: ActingProfileManager = Depends(get_acting_profile_manager),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> BusinessProfilePage:
    """Owner-admin panel's full company list -- unlike the public `listBusinessProfiles`,
    includes ARCHIVED profiles and reports a real `page.total` (used for the panel's "total
    companies" stat card)."""
    page_limit = _clamp_limit(limit)
    profiles, next_cursor = await use_cases.list_admin_profiles(
        status=status, cursor=cursor, limit=page_limit
    )
    total = await use_cases.count_profiles()
    return BusinessProfilePage(
        items=[await _to_profile_dto(profile, use_cases=use_cases) for profile in profiles],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor, total=total),
    )


@admin_profiles_router.post(
    "/admin/business-profiles/{profileId}/archive", operation_id="adminArchiveBusinessProfile"
)
async def admin_archive_business_profile(
    profileId: UUID,
    _manager: ActingProfileManager = Depends(get_acting_profile_manager),
    use_cases: ProfileUseCases = Depends(get_profile_use_cases),
) -> BusinessProfileDto:
    """Owner-admin panel's "remove company" action. Archives rather than hard-deletes (same
    anonymise/retain-over-hard-delete discipline `identity.UserAccount.close` uses for users) --
    the profile disappears from every public listing immediately, its data/audit trail is kept."""
    profile = await use_cases.admin_archive_profile(
        BusinessProfileId(value=profileId), now=datetime.now(UTC)
    )
    return await _to_profile_dto(profile, use_cases=use_cases)
