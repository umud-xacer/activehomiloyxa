"""Registers identity's typed domain/application exceptions onto the shared
`backbone.errors.ExceptionMapper` (the same registry `configuration.interfaces.errors` extends --
"a later module task registers its own typed domain exceptions against this same registry").
Called once from the composition root (`apps/backend/src/main.py`).

Status/code choices follow `contracts/errors/problem.py`'s closed `ErrorCode` vocabulary and, for
the endpoints affected, Security Sec 4.2's four-gate framing: `PERMISSION_DENIED` for Gate 3
(no permission held -- default-deny), `WRONG_ACTING_PROFILE` for Gate 2/4 (I-10 scoping). A few
exceptions are shared across endpoints with different *declared* response sets in
contracts/openapi.yaml (e.g. `verifyOtp` lists only 200/422/429 -- no 401); the mapping below is
one global choice per exception type (the same pattern `configuration.interfaces.errors` already
uses), so `OtpPurposeMismatchError`/`InvalidCredentialsError` are deliberately two distinct
exception types with two different statuses (422 vs. 401) rather than one exception forced to
serve both -- see the exceptions' own docstrings in `identity/domain/exceptions.py`.
"""

from __future__ import annotations

from backbone.errors import ExceptionMapper, simple_problem_builder
from identity.application.exceptions import (
    AccountNotFoundError,
    InvalidAppleCredentialError,
    InvalidGoogleCredentialError,
    InvalidSessionTokenError,
    OtpChallengeNotFoundError,
    OtpProviderUnavailableError,
    RecoveryTargetRequiredError,
    RoleDefinitionNotFoundError,
    SessionNotFoundError,
)
from identity.domain import (
    AccountNotActiveError,
    DuplicateContactError,
    IllegalAccountStateTransitionError,
    InvalidCredentialsError,
    LoginLockedOutError,
    OtpAlreadyConsumedError,
    OtpAttemptsExceededError,
    OtpCodeMismatchError,
    OtpExpiredError,
    OtpPurposeMismatchError,
    OtpThrottledError,
    PermissionDeniedError,
    ProfileNotOwnedError,
    RoleNotAssignedError,
    SessionExpiredError,
    SessionRevokedError,
    UnknownAuthenticationMethodError,
    WrongActingProfileError,
)


def register_identity_exception_mappings(mapper: ExceptionMapper) -> None:
    # --- authentication (401) ---------------------------------------------------------------
    mapper.register(
        InvalidCredentialsError,
        simple_problem_builder(
            status=401, code="AUTHENTICATION_INVALID", title="Invalid credentials"
        ),
    )
    mapper.register(
        InvalidGoogleCredentialError,
        simple_problem_builder(
            status=401, code="AUTHENTICATION_INVALID", title="Invalid Google credential"
        ),
    )
    mapper.register(
        InvalidAppleCredentialError,
        simple_problem_builder(
            status=401, code="AUTHENTICATION_INVALID", title="Invalid Apple credential"
        ),
    )
    mapper.register(
        InvalidSessionTokenError,
        simple_problem_builder(
            status=401, code="AUTHENTICATION_REQUIRED", title="No valid session"
        ),
    )
    mapper.register(
        SessionExpiredError,
        simple_problem_builder(status=401, code="SESSION_EXPIRED", title="Session has expired"),
    )
    mapper.register(
        SessionRevokedError,
        simple_problem_builder(status=401, code="SESSION_EXPIRED", title="Session was revoked"),
    )

    # --- authorization (403, Security Sec 4.2 Gates 3-4) ---------------------------------------
    mapper.register(
        PermissionDeniedError,
        simple_problem_builder(
            status=403, code="PERMISSION_DENIED", title="Caller lacks the required permission"
        ),
    )
    mapper.register(
        WrongActingProfileError,
        simple_problem_builder(
            status=403,
            code="WRONG_ACTING_PROFILE",
            title="Acting profile is not authorized for this scope",
        ),
    )
    mapper.register(
        ProfileNotOwnedError,
        simple_problem_builder(
            status=403,
            code="WRONG_ACTING_PROFILE",
            title="Account does not own the requested acting profile",
        ),
    )
    mapper.register(
        AccountNotActiveError,
        simple_problem_builder(status=403, code="PERMISSION_DENIED", title="Account is not active"),
    )

    # --- not found (404) -------------------------------------------------------------------
    mapper.register(
        AccountNotFoundError,
        simple_problem_builder(status=404, code="RESOURCE_NOT_FOUND", title="Account not found"),
    )
    mapper.register(
        SessionNotFoundError,
        simple_problem_builder(status=404, code="RESOURCE_NOT_FOUND", title="Session not found"),
    )
    mapper.register(
        RoleNotAssignedError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Role is not assigned to this account"
        ),
    )
    mapper.register(
        RoleDefinitionNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="No published role with that code"
        ),
    )

    # --- conflict (409) ---------------------------------------------------------------------
    mapper.register(
        DuplicateContactError,
        simple_problem_builder(
            status=409, code="DUPLICATE_KEY", title="Phone or email already registered"
        ),
    )
    mapper.register(
        IllegalAccountStateTransitionError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Account cannot transition to that status",
        ),
    )
    mapper.register(
        UnknownAuthenticationMethodError,
        simple_problem_builder(
            status=409,
            code="CONFLICT",
            title="Account has no authentication method of that kind",
        ),
    )

    # --- validation (422) -- OTP verify failures (verifyOtp declares only 200/422/429) --------
    mapper.register(
        OtpChallengeNotFoundError,
        simple_problem_builder(
            status=422, code="VALIDATION_FAILED", title="No active OTP challenge for this phone"
        ),
    )
    mapper.register(
        OtpExpiredError,
        simple_problem_builder(status=422, code="VALIDATION_FAILED", title="OTP has expired"),
    )
    mapper.register(
        OtpAlreadyConsumedError,
        simple_problem_builder(status=422, code="VALIDATION_FAILED", title="OTP was already used"),
    )
    mapper.register(
        OtpCodeMismatchError,
        simple_problem_builder(
            status=422, code="VALIDATION_FAILED", title="OTP code does not match"
        ),
    )
    mapper.register(
        OtpAttemptsExceededError,
        simple_problem_builder(
            status=422,
            code="BUSINESS_RULE_VIOLATION",
            title="Too many incorrect attempts for this OTP challenge",
        ),
    )
    mapper.register(
        OtpPurposeMismatchError,
        simple_problem_builder(
            status=422,
            code="VALIDATION_FAILED",
            title="No registered account for this phone/purpose",
        ),
    )
    mapper.register(
        RecoveryTargetRequiredError,
        simple_problem_builder(
            status=422, code="VALIDATION_FAILED", title="Phone or email is required"
        ),
    )

    # --- rate limiting (429) -----------------------------------------------------------------
    mapper.register(
        OtpThrottledError,
        simple_problem_builder(
            status=429, code="OTP_THROTTLED", title="Too many OTP requests, try again later"
        ),
    )
    mapper.register(
        LoginLockedOutError,
        simple_problem_builder(
            status=429,
            code="RATE_LIMITED",
            title="Too many failed login attempts, try again later",
        ),
    )

    # --- degraded external dependency (503) -------------------------------------------------
    mapper.register(
        OtpProviderUnavailableError,
        simple_problem_builder(
            status=503,
            code="DEPENDENCY_DEGRADED",
            title="SMS provider is temporarily unavailable",
        ),
    )
