"""The exception -> Problem mapping registry (API contract: one Problem-style envelope,
CLAUDE.md; Playbook Sec 6 "map domain/validation/authorization failures to the correct stable
code and HTTP status ... never leak stack traces ... never swallow exceptions silently").

Extensible by design: no real domain/application exception types exist yet (P-03 is
infrastructure-only), so this registers only the two mappings a module-less app skeleton can
actually exercise -- FastAPI/Pydantic request validation, and the unhandled-exception fallback.
A later module task registers its own typed domain exceptions against this same registry
(`mapper.register(QuotaExceededError, simple_problem_builder(status=409, code="QUOTA_EXCEEDED",
title="Quota exceeded"))`) rather than building a new mapping mechanism.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from fastapi.exceptions import RequestValidationError

from contracts.errors import ErrorCode, Problem, ValidationError

ProblemBuilder = Callable[[Exception], Problem]
"""Builds the full `Problem` (status included) from the exception instance -- a callable, not a
fixed template, so a mapping can inspect the exception for per-instance detail (e.g. per-field
validation errors) when it needs to, and stay a one-liner when it doesn't (`simple_problem_builder`)."""


class ExceptionMapper:
    """Maps an exception instance to the `Problem` it becomes on the wire. Lookup walks the
    exception's MRO, so a subclass registered after its parent shadows the parent's mapping for
    instances of that subclass specifically."""

    def __init__(self) -> None:
        self._builders: dict[type[Exception], ProblemBuilder] = {}

    def register(self, exc_type: type[Exception], builder: ProblemBuilder) -> None:
        self._builders[exc_type] = builder

    def resolve(self, exc: Exception) -> Problem | None:
        for exc_type in type(exc).__mro__:
            builder = self._builders.get(exc_type)
            if builder is not None:
                return builder(exc)
        return None


def simple_problem_builder(
    *,
    status: int,
    code: ErrorCode,
    title: str,
    detail: str | None = None,
) -> ProblemBuilder:
    """The common case: a fixed status/code/title/detail regardless of the specific exception
    instance -- covers most typed domain exceptions a later task registers."""

    def build(_exc: Exception) -> Problem:
        return Problem(
            type=f"https://errors.activehome.uz/{code.lower().replace('_', '-')}",
            title=title,
            status=status,
            code=code,
            detail=detail,
            trace_id="",  # filled in by the middleware, which knows the request's traceId
        )

    return build


def _validation_problem_builder(exc: Exception) -> Problem:
    # Only ever invoked with a `RequestValidationError` -- `ExceptionMapper.resolve()` looks the
    # builder up by walking `type(exc).__mro__` and only calls it when this exact type matches,
    # so the narrowing here is a guaranteed-by-construction fact, not a runtime check: `cast`,
    # not `assert` (an `assert` would be stripped under `-O`, silently reintroducing the same
    # `AttributeError` a bare `Exception` would raise on `.errors()` below).
    exc = cast(RequestValidationError, exc)
    field_errors = [
        ValidationError(
            path="/" + "/".join(str(p) for p in err["loc"]),
            rule=err["type"],
            message=err["msg"],
        )
        for err in exc.errors()
    ]
    return Problem(
        type="https://errors.activehome.uz/validation",
        title="Validation failed",
        status=422,
        code="VALIDATION_FAILED",
        detail="One or more fields failed validation.",
        trace_id="",
        errors=field_errors,
    )


def default_exception_mapper() -> ExceptionMapper:
    """The baseline registrations every app instance needs regardless of which modules exist."""
    mapper = ExceptionMapper()
    mapper.register(RequestValidationError, _validation_problem_builder)
    return mapper
