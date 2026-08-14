"""Registers profiles' typed domain/application exceptions onto the shared `backbone.errors.
ExceptionMapper` (the same registry `catalog.interfaces.errors`/`billing.interfaces.errors`
extend). Called once from the composition root (`apps/backend/src/main.py`).
"""

from __future__ import annotations

from backbone.errors import ExceptionMapper, simple_problem_builder
from profiles.application.exceptions import (
    MediaAssetNotFoundError,
    NotProfileOwnerError,
    ProfileNotFoundError,
    ProfileNotPubliclyVisibleError,
    VerificationCaseNotFoundError,
    VerificationNotEligibleError,
)
from profiles.domain.exceptions import (
    BadgeNotIssuableWithoutApprovedCaseError,
    DuplicateDocumentPositionError,
    IllegalBadgeTransitionError,
    IllegalProfileStatusTransitionError,
    IllegalVerificationCaseStateTransitionError,
    NoDocumentsSubmittedError,
    OnboardingAlreadyCompletedError,
    OnboardingIncompleteError,
    PortfolioItemLimitExceededError,
    PortfolioItemNotFoundError,
    TerminalVerificationCaseError,
)


def register_profiles_exception_mappings(mapper: ExceptionMapper) -> None:
    # --- validation (422) -----------------------------------------------------------------------
    mapper.register(
        PortfolioItemLimitExceededError,
        simple_problem_builder(
            status=422,
            code="VALIDATION_FAILED",
            title="A business profile may hold at most fifty portfolio items",
        ),
    )
    mapper.register(
        NoDocumentsSubmittedError,
        simple_problem_builder(
            status=422,
            code="VALIDATION_FAILED",
            title="Verification requires at least one submitted document",
        ),
    )
    mapper.register(
        OnboardingIncompleteError,
        simple_problem_builder(
            status=422,
            code="VALIDATION_FAILED",
            title="Business profile is missing a required onboarding field",
        ),
    )
    mapper.register(
        DuplicateDocumentPositionError,
        simple_problem_builder(
            status=422,
            code="VALIDATION_FAILED",
            title="Submitted document positions must be unique and contiguous",
        ),
    )

    # --- business rule (403, matches the contract's own 403 on requestVerification) -------------
    mapper.register(
        VerificationNotEligibleError,
        simple_problem_builder(
            status=403,
            code="BUSINESS_RULE_VIOLATION",
            title="No active paid verification entitlement for this business profile",
        ),
    )
    mapper.register(
        BadgeNotIssuableWithoutApprovedCaseError,
        simple_problem_builder(
            status=409,
            code="BUSINESS_RULE_VIOLATION",
            title="A verified badge may only be issued from an approved verification case",
        ),
    )

    # --- authorization (403) --------------------------------------------------------------------
    mapper.register(
        NotProfileOwnerError,
        simple_problem_builder(
            status=403, code="PERMISSION_DENIED", title="Caller does not own this business profile"
        ),
    )

    # --- not found (404) -----------------------------------------------------------------------
    mapper.register(
        ProfileNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Business profile not found"
        ),
    )
    mapper.register(
        VerificationCaseNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Verification case not found"
        ),
    )
    mapper.register(
        MediaAssetNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Media asset not found"
        ),
    )
    mapper.register(
        PortfolioItemNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="No such portfolio item"
        ),
    )
    mapper.register(
        ProfileNotPubliclyVisibleError,
        simple_problem_builder(
            status=404,
            code="RESOURCE_NOT_FOUND",
            title="Business profile not found",
        ),
    )

    # --- conflict (409) ------------------------------------------------------------------------
    mapper.register(
        IllegalProfileStatusTransitionError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Business profile cannot make that transition",
        ),
    )
    mapper.register(
        IllegalBadgeTransitionError,
        simple_problem_builder(
            status=409, code="ILLEGAL_STATE_TRANSITION", title="Badge cannot make that transition"
        ),
    )
    mapper.register(
        IllegalVerificationCaseStateTransitionError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Verification case cannot make that transition",
        ),
    )
    mapper.register(
        TerminalVerificationCaseError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Verification case is terminal and cannot be modified",
        ),
    )
    mapper.register(
        OnboardingAlreadyCompletedError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Business profile has already completed onboarding",
        ),
    )
