"""profiles/domain -- the BusinessProfile and VerificationCase aggregates, their PortfolioItem/
SubmittedDocument child entities, value objects, policies, and typed exceptions (Task P-11).
Imports `shared_kernel` only (Clean Architecture rule 1); never imported by another module
(`domain/` is never part of a module's public surface, AIR-02).
"""

from __future__ import annotations

from profiles.domain.business_profile import MAX_PORTFOLIO_ITEMS, BusinessProfile
from profiles.domain.exceptions import (
    BadgeNotIssuableWithoutApprovedCaseError,
    DuplicateDocumentPositionError,
    IllegalBadgeTransitionError,
    IllegalProfileStatusTransitionError,
    IllegalVerificationCaseStateTransitionError,
    NoDocumentsSubmittedError,
    PortfolioItemLimitExceededError,
    PortfolioItemNotFoundError,
    ProfilesDomainError,
    TerminalVerificationCaseError,
)
from profiles.domain.policies import (
    VERIFICATION_SLA_HOURS,
    compute_sla_due_at,
    order_queue,
)
from profiles.domain.portfolio_item import PortfolioItem
from profiles.domain.submitted_document import SubmittedDocument
from profiles.domain.value_objects import (
    TERMINAL_CASE_STATUSES,
    BadgeStatus,
    CaseStatus,
    Decision,
    ProfileStatus,
    ProfileType,
    VerifiedBadge,
)
from profiles.domain.verification_case import (
    MAX_DOCUMENTS,
    ApprovedVerificationProof,
    VerificationCase,
)

__all__ = [
    "MAX_DOCUMENTS",
    "MAX_PORTFOLIO_ITEMS",
    "TERMINAL_CASE_STATUSES",
    "VERIFICATION_SLA_HOURS",
    "ApprovedVerificationProof",
    "BadgeNotIssuableWithoutApprovedCaseError",
    "BadgeStatus",
    "BusinessProfile",
    "CaseStatus",
    "Decision",
    "DuplicateDocumentPositionError",
    "IllegalBadgeTransitionError",
    "IllegalProfileStatusTransitionError",
    "IllegalVerificationCaseStateTransitionError",
    "NoDocumentsSubmittedError",
    "PortfolioItem",
    "PortfolioItemLimitExceededError",
    "PortfolioItemNotFoundError",
    "ProfileStatus",
    "ProfileType",
    "ProfilesDomainError",
    "SubmittedDocument",
    "TerminalVerificationCaseError",
    "VerificationCase",
    "VerifiedBadge",
    "compute_sla_due_at",
    "order_queue",
]
