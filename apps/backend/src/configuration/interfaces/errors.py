"""Registers the configuration module's typed exceptions onto the shared
`backbone.errors.ExceptionMapper` (the extension point that module's own docstring names:
"a later module task registers its own typed domain exceptions against this same registry ...
rather than building a new mapping mechanism"). Called once from the composition root
(`apps/backend/src/main.py`).
"""

from __future__ import annotations

from typing import cast

from backbone.errors import ExceptionMapper, simple_problem_builder
from configuration.application.exceptions import (
    ConfigHeadNotFoundError,
    ConfigVersionNotFoundError,
    GateFailedError,
    InvalidDraftRequestError,
    OwnerAdminAccessLockedOutError,
    VersionNotPublishableError,
)
from configuration.domain import (
    ApproverPermissionError,
    DraftRequiredError,
    DuplicateCodeError,
    SelfApprovalError,
    WhitelistViolationError,
)
from configuration.interfaces.auth import PermissionDeniedError
from contracts.errors import Problem, ValidationError


def _gate_failed_builder(exc: Exception) -> Problem:
    # `ExceptionMapper.resolve` only ever invokes this builder for a registered `GateFailedError`
    # (see `register_configuration_exception_mappings` below) -- a `cast`, not an `assert`, since
    # Security Architecture I-5 forbids `assert` gating control flow in `src/` (it strips under
    # `-O`; `tools/security/bandit.yaml` B101 fails the QG-07 SAST scan on it).
    gate_failed = cast(GateFailedError, exc)
    field_errors = [
        ValidationError(
            path=f"/{error.field}" if error.field else "/",
            rule=error.code,
            message=error.message,
        )
        for error in gate_failed.result.errors
    ]
    return Problem(
        type="https://errors.activehome.uz/validation",
        title="Validation gate failed",
        status=422,
        code="VALIDATION_FAILED",
        detail="The configuration content failed one or more pre-activation checks (Config "
        "Framework Sec 9).",
        trace_id="",
        errors=field_errors,
    )


def register_configuration_exception_mappings(mapper: ExceptionMapper) -> None:
    mapper.register(
        ConfigHeadNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Configuration head not found"
        ),
    )
    mapper.register(
        ConfigVersionNotFoundError,
        simple_problem_builder(
            status=404,
            code="RESOURCE_NOT_FOUND",
            title="Configuration version not found",
        ),
    )
    mapper.register(
        DuplicateCodeError,
        simple_problem_builder(
            status=409, code="DUPLICATE_KEY", title="Duplicate configuration code"
        ),
    )
    mapper.register(
        VersionNotPublishableError,
        simple_problem_builder(
            status=409,
            code="CONFLICT",
            title="Version is not publishable from its current status",
        ),
    )
    mapper.register(
        DraftRequiredError,
        simple_problem_builder(
            status=409,
            code="CONFLICT",
            title="Version is not a draft (already published)",
        ),
    )
    mapper.register(GateFailedError, _gate_failed_builder)
    mapper.register(
        ApproverPermissionError,
        simple_problem_builder(
            status=403,
            code="PERMISSION_DENIED",
            title="Approver lacks the required approve-permission key",
        ),
    )
    mapper.register(
        SelfApprovalError,
        simple_problem_builder(
            status=403,
            code="PERMISSION_DENIED",
            title="The approver must be a different principal from the author",
        ),
    )
    mapper.register(
        WhitelistViolationError,
        simple_problem_builder(
            status=422, code="VALIDATION_FAILED", title="Whitelist membership violation"
        ),
    )
    mapper.register(
        PermissionDeniedError,
        simple_problem_builder(
            status=403,
            code="PERMISSION_DENIED",
            title="Caller lacks the required permission",
        ),
    )
    mapper.register(
        InvalidDraftRequestError,
        simple_problem_builder(
            status=422,
            code="VALIDATION_FAILED",
            title="Invalid configuration draft request",
        ),
    )
    mapper.register(
        OwnerAdminAccessLockedOutError,
        simple_problem_builder(
            status=429,
            code="RATE_LIMITED",
            title="Too many failed owner-admin-access attempts, try again later",
        ),
    )
