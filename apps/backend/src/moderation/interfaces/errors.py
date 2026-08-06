"""Registers moderation's typed domain/application exceptions onto the shared `backbone.errors.
ExceptionMapper` (the same registry `profiles.interfaces.errors`/`catalog.interfaces.errors`
extend). Called once from the composition root (`apps/backend/src/main.py`).
"""

from __future__ import annotations

from backbone.errors import ExceptionMapper, simple_problem_builder
from moderation.application.exceptions import ModerationCaseNotFoundError
from moderation.domain.exceptions import (
    IllegalModerationCaseStateTransitionError,
    InvalidResolutionForSubjectError,
    TerminalModerationCaseError,
)


def register_moderation_exception_mappings(mapper: ExceptionMapper) -> None:
    # --- validation (422) -----------------------------------------------------------------------
    mapper.register(
        InvalidResolutionForSubjectError,
        simple_problem_builder(
            status=422,
            code="VALIDATION_FAILED",
            title="This resolution action is not valid for the case's subject type",
        ),
    )

    # --- not found (404) -----------------------------------------------------------------------
    mapper.register(
        ModerationCaseNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Moderation case not found"
        ),
    )

    # --- conflict (409) ------------------------------------------------------------------------
    mapper.register(
        IllegalModerationCaseStateTransitionError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Moderation case cannot make that transition",
        ),
    )
    mapper.register(
        TerminalModerationCaseError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Moderation case is terminal and cannot be modified",
        ),
    )
