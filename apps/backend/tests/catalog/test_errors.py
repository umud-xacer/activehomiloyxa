"""`register_catalog_exception_mappings`'s one non-trivial builder --
`_attribute_validation_problem_builder` turns each `AttributeValidationError.failures` entry
("<path>: <message>") into a `ValidationError`, unlike every other registration in that module
(a one-line `simple_problem_builder` call). No real HTTP path happens to exercise a multi-failure
`AttributeValidationError` end to end, so this drives the mapping directly through the same public
`ExceptionMapper.resolve()` surface a real request handler uses.
"""

from __future__ import annotations

from backbone.errors import ExceptionMapper
from catalog.domain.exceptions import AttributeValidationError
from catalog.interfaces.errors import register_catalog_exception_mappings
from contracts.errors import ValidationError


def test_attribute_validation_error_becomes_a_422_with_one_field_error_per_failure() -> None:
    mapper = ExceptionMapper()
    register_catalog_exception_mappings(mapper)

    exc = AttributeValidationError(
        failures=(
            "area_sqm: must be a positive number",
            "rooms: required",
        )
    )

    problem = mapper.resolve(exc)

    assert problem is not None
    assert problem.status == 422
    assert problem.code == "VALIDATION_FAILED"
    assert problem.errors == [
        ValidationError(
            path="/attributes/area_sqm",
            rule="attribute_validation",
            message="must be a positive number",
        ),
        ValidationError(path="/attributes/rooms", rule="attribute_validation", message="required"),
    ]
