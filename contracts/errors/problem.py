"""The frozen Problem-style error envelope (RFC-9457 shaped) -- `contracts/openapi.yaml`
`components/schemas/Error` and `ValidationError`, copied field-for-field. Every module's
`interfaces/` ports use `Problem` as the error type for the requests they can reject; this is
the single definition every module imports rather than redeclaring (API contract, CLAUDE.md
"Errors are one Problem-style envelope").

STATUS: frozen (Task P-01). Schema only -- no raising/handling logic. Changing the `code`
vocabulary or a required field is a breaking API change and needs an ADR (Playbook Sec 18).
"""

from __future__ import annotations

from typing import Literal

from active_home_shared import CamelModel

ErrorCode = Literal[
    "VALIDATION_FAILED",
    "BUSINESS_RULE_VIOLATION",
    "AUTHENTICATION_REQUIRED",
    "AUTHENTICATION_INVALID",
    "SESSION_EXPIRED",
    "PERMISSION_DENIED",
    "WRONG_ACTING_PROFILE",
    "RESOURCE_NOT_FOUND",
    "CONFLICT",
    "DUPLICATE_KEY",
    "ILLEGAL_STATE_TRANSITION",
    "QUOTA_EXCEEDED",
    "IMAGE_COUNT_EXCEEDED",
    "UNSUPPORTED_MEDIA_TYPE",
    "IDEMPOTENCY_KEY_REUSED",
    "RATE_LIMITED",
    "OTP_THROTTLED",
    "DEPENDENCY_DEGRADED",
]
"""The closed vocabulary for `Problem.code` (OpenAPI `Error.code`). Adding a member is an API
contract change (needs an ADR), not a routine edit."""


class ValidationError(CamelModel):
    """One field-level validation failure (OpenAPI `ValidationError`)."""

    path: str
    """JSON pointer / field path, e.g. "/attributes/area_m2"."""
    rule: str
    """The whitelisted validator or schema rule that failed, e.g. "numeric_range"."""
    message: str


class Problem(CamelModel):
    """Single Problem-style error envelope (RFC-9457 shaped). `code` is a stable,
    machine-readable member of a closed vocabulary and refines the HTTP status
    (OpenAPI `Error`)."""

    type: str
    """URI reference identifying the problem type, e.g. "https://errors.activehome.uz/validation"."""
    title: str
    """Short, human-readable summary."""
    status: int
    """HTTP status code."""
    code: ErrorCode
    detail: str | None = None
    """Human-readable explanation for this occurrence."""
    instance: str | None = None
    """URI reference for this specific occurrence."""
    trace_id: str
    errors: list[ValidationError] | None = None
