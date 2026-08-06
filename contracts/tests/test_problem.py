"""contracts/errors/problem.py -- the Problem envelope round-trips through its camelCase wire
alias (`traceId`) and rejects a `code` outside the closed vocabulary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from contracts.errors import Problem, ValidationError


def test_FR_CONTRACT_003_problem_round_trips_camel_case_trace_id() -> None:
    problem = Problem(
        type="https://errors.activehome.uz/validation",
        title="Validation failed",
        status=422,
        code="VALIDATION_FAILED",
        trace_id="abc-123",
        errors=[
            ValidationError(path="/attributes/area_m2", rule="numeric_range", message="too small")
        ],
    )
    wire = problem.model_dump(by_alias=True, mode="json")
    assert wire["traceId"] == "abc-123"
    assert wire["errors"][0]["path"] == "/attributes/area_m2"

    rebuilt = Problem.model_validate(wire)
    assert rebuilt == problem


def test_I05_problem_code_is_closed_vocabulary() -> None:
    """# enforces the OpenAPI `Error.code` closed vocabulary (Playbook Sec 18: adding a member
    is an API contract change, not a routine edit)."""
    with pytest.raises(PydanticValidationError):
        Problem(
            type="https://errors.activehome.uz/x",
            title="x",
            status=400,
            code="NOT_A_REAL_CODE",  # type: ignore[arg-type]
            trace_id="t",
        )
