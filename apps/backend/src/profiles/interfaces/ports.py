"""profiles -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from profiles.interfaces.dto import (
    BusinessProfile,
    BusinessProfileCreateRequest,
    BusinessProfilePage,
    BusinessProfileUpdateRequest,
    PortfolioItem,
    TeamMember,
    VerificationCase,
    VerificationCasePage,
    VerificationDecisionRequest,
    VerificationRequestCreate,
)


class ProfileQueryPort(Protocol):
    """Derived from OpenAPI operations: `addPortfolioItem`, `addTeamMember`, `archiveBusinessProfile`, `createBusinessProfile`, `getBusinessProfile`, `listBusinessProfiles`, `listPortfolio`, `listTeamMembers`, `removePortfolioItem`, `removeTeamMember`, `updateBusinessProfile`."""

    async def add_portfolio_item(self, profile_id: UUID, body: PortfolioItem) -> PortfolioItem:
        """`POST /business-profiles/{profileId}/portfolio` (operationId `addPortfolioItem`). Add a portfolio item"""
        ...

    async def add_team_member(self, profile_id: UUID, body: TeamMember) -> TeamMember:
        """`POST /business-profiles/{profileId}/team` (operationId `addTeamMember`). Add a team member"""
        ...

    async def archive_business_profile(self, profile_id: UUID) -> None:
        """`DELETE /business-profiles/{profileId}` (operationId `archiveBusinessProfile`). Archive a business profile"""
        ...

    async def create_business_profile(self, body: BusinessProfileCreateRequest) -> BusinessProfile:
        """`POST /business-profiles` (operationId `createBusinessProfile`). Create a company profile"""
        ...

    async def get_business_profile(self, profile_id: UUID) -> BusinessProfile:
        """`GET /business-profiles/{profileId}` (operationId `getBusinessProfile`). Get a business profile"""
        ...

    async def list_business_profiles(
        self,
        cursor: str | None = None,
        limit: int | None = 20,
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
        | None = None,
        verified_only: bool | None = None,
    ) -> BusinessProfilePage:
        """`GET /business-profiles` (operationId `listBusinessProfiles`). List business profiles"""
        ...

    async def list_portfolio(self, profile_id: UUID) -> list[PortfolioItem]:
        """`GET /business-profiles/{profileId}/portfolio` (operationId `listPortfolio`). List portfolio items"""
        ...

    async def list_team_members(self, profile_id: UUID) -> list[TeamMember]:
        """`GET /business-profiles/{profileId}/team` (operationId `listTeamMembers`). List team members"""
        ...

    async def remove_portfolio_item(self, profile_id: UUID, item_id: UUID) -> None:
        """`DELETE /business-profiles/{profileId}/portfolio/{itemId}` (operationId `removePortfolioItem`). Remove a portfolio item"""
        ...

    async def remove_team_member(self, profile_id: UUID, user_id: UUID) -> None:
        """`DELETE /business-profiles/{profileId}/team/{userId}` (operationId `removeTeamMember`). Remove a team member"""
        ...

    async def update_business_profile(
        self, profile_id: UUID, body: BusinessProfileUpdateRequest
    ) -> BusinessProfile:
        """`PATCH /business-profiles/{profileId}` (operationId `updateBusinessProfile`). Manage a business profile"""
        ...


class VerificationPort(Protocol):
    """Derived from OpenAPI operations: `decideVerification`, `getVerificationCase`, `listVerificationQueue`, `requestVerification`."""

    async def decide_verification(
        self, case_id: UUID, body: VerificationDecisionRequest
    ) -> VerificationCase:
        """`POST /admin/verification-queue/{caseId}/decision` (operationId `decideVerification`). Decide a verification case"""
        ...

    async def get_verification_case(self, profile_id: UUID) -> VerificationCase:
        """`GET /business-profiles/{profileId}/verification` (operationId `getVerificationCase`). Get the current verification case"""
        ...

    async def list_verification_queue(
        self,
        status: Literal["REQUESTED", "IN_REVIEW", "APPROVED", "REJECTED"] | None = None,
        cursor: str | None = None,
        limit: int | None = 20,
    ) -> VerificationCasePage:
        """`GET /admin/verification-queue` (operationId `listVerificationQueue`). List verification cases"""
        ...

    async def request_verification(
        self, profile_id: UUID, body: VerificationRequestCreate
    ) -> VerificationCase:
        """`POST /business-profiles/{profileId}/verification` (operationId `requestVerification`). Request business verification"""
        ...
