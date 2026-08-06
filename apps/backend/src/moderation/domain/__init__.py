"""moderation/domain -- the ModerationCase aggregate, value objects, policies, and typed
exceptions (Task P-12). Imports `shared_kernel` only (Clean Architecture rule 1); never imported
by another module (`domain/` is never part of a module's public surface, AIR-02).
"""

from __future__ import annotations

from moderation.domain.exceptions import (
    IllegalModerationCaseStateTransitionError,
    InvalidResolutionForSubjectError,
    ModerationDomainError,
    TerminalModerationCaseError,
)
from moderation.domain.moderation_case import ModerationCase
from moderation.domain.policies import POST_PUBLICATION_MODERATION, order_queue
from moderation.domain.value_objects import (
    ACTIONS_BY_SUBJECT_TYPE,
    TERMINAL_CASE_STATUSES,
    CaseStatus,
    Origin,
    OriginType,
    Resolution,
    ResolutionAction,
    Subject,
    SubjectType,
)

__all__ = [
    "ACTIONS_BY_SUBJECT_TYPE",
    "POST_PUBLICATION_MODERATION",
    "TERMINAL_CASE_STATUSES",
    "CaseStatus",
    "IllegalModerationCaseStateTransitionError",
    "InvalidResolutionForSubjectError",
    "ModerationCase",
    "ModerationDomainError",
    "Origin",
    "OriginType",
    "Resolution",
    "ResolutionAction",
    "Subject",
    "SubjectType",
    "TerminalModerationCaseError",
    "order_queue",
]
