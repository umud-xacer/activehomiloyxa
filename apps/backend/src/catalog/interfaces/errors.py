"""Registers catalog's typed domain/application exceptions onto the shared
`backbone.errors.ExceptionMapper` (the same registry `identity.interfaces.errors`/`media.
interfaces.errors` extend). Called once from the composition root (`apps/backend/src/main.py`).

Status/code choices follow `contracts/errors/problem.py`'s closed `ErrorCode` vocabulary --
`QUOTA_EXCEEDED`/`IMAGE_COUNT_EXCEEDED` are literal members of that vocabulary anticipating
exactly `QuotaExceededError`/`ImageLimitExceededError` (I-08/I-04); `backbone.errors.mapping`'s
own module docstring gives `QuotaExceededError -> 409 QUOTA_EXCEEDED` as its worked example,
followed here verbatim.
"""

from __future__ import annotations

from typing import cast

from backbone.errors import ExceptionMapper, simple_problem_builder
from catalog.application.exceptions import (
    CategoryFormUnavailableError,
    CategoryNotFoundError,
    FavoriteNotFoundError,
    ListingMediaAssetNotFoundError,
    ListingNotFoundError,
    StaleListingVersionError,
)
from catalog.domain.exceptions import (
    AttributeValidationError,
    DuplicateImagePositionError,
    IllegalListingStateTransitionError,
    ImageAttachmentNotFoundError,
    ImageLimitExceededError,
    ListingAlreadyFlaggedError,
    ListingNotFlaggedError,
    NotListingOwnerError,
    QuotaExceededError,
)
from contracts.errors import Problem, ValidationError


def _attribute_validation_problem_builder(exc: Exception) -> Problem:
    # Only ever invoked with an `AttributeValidationError` -- registered below via
    # `mapper.register(AttributeValidationError, ...)`, and `ExceptionMapper.resolve()` only
    # calls a builder when the exception's own MRO matches its registered type. `cast`, not
    # `assert`: the narrowing is a guaranteed-by-construction fact, not a runtime check.
    exc = cast(AttributeValidationError, exc)
    field_errors = []
    for failure in exc.failures:
        path, _, message = failure.partition(": ")
        field_errors.append(
            ValidationError(
                path=f"/attributes/{path}", rule="attribute_validation", message=message
            )
        )
    return Problem(
        type="https://errors.activehome.uz/validation",
        title="Attribute validation failed",
        status=422,
        code="VALIDATION_FAILED",
        detail="One or more attributes failed validation against the bound form.",
        trace_id="",
        errors=field_errors,
    )


def register_catalog_exception_mappings(mapper: ExceptionMapper) -> None:
    # --- validation (422) ---------------------------------------------------------------------
    mapper.register(AttributeValidationError, _attribute_validation_problem_builder)
    mapper.register(
        ImageLimitExceededError,
        simple_problem_builder(
            status=422,
            code="IMAGE_COUNT_EXCEEDED",
            title="A listing may carry at most ten image attachments",
        ),
    )
    mapper.register(
        DuplicateImagePositionError,
        simple_problem_builder(
            status=422,
            code="VALIDATION_FAILED",
            title="Image reorder does not match the current attachments",
        ),
    )
    mapper.register(
        CategoryFormUnavailableError,
        simple_problem_builder(
            status=503,
            code="DEPENDENCY_DEGRADED",
            title="This category has no published form to validate against",
        ),
    )

    # --- quota (409, backbone.errors.mapping's own worked example) ----------------------------
    mapper.register(
        QuotaExceededError,
        simple_problem_builder(status=409, code="QUOTA_EXCEEDED", title="Listing quota exceeded"),
    )

    # --- authorization (403) --------------------------------------------------------------------
    mapper.register(
        NotListingOwnerError,
        simple_problem_builder(
            status=403, code="PERMISSION_DENIED", title="Caller does not own this listing"
        ),
    )

    # --- not found (404) -----------------------------------------------------------------------
    mapper.register(
        ListingNotFoundError,
        simple_problem_builder(status=404, code="RESOURCE_NOT_FOUND", title="Listing not found"),
    )
    mapper.register(
        FavoriteNotFoundError,
        simple_problem_builder(status=404, code="RESOURCE_NOT_FOUND", title="Favorite not found"),
    )
    mapper.register(
        CategoryNotFoundError,
        simple_problem_builder(status=404, code="RESOURCE_NOT_FOUND", title="Category not found"),
    )
    mapper.register(
        ListingMediaAssetNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Media asset not found"
        ),
    )
    mapper.register(
        ImageAttachmentNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="No such image attachment"
        ),
    )

    # --- conflict (409) ------------------------------------------------------------------------
    mapper.register(
        IllegalListingStateTransitionError,
        simple_problem_builder(
            status=409, code="ILLEGAL_STATE_TRANSITION", title="Listing cannot make that transition"
        ),
    )
    mapper.register(
        ListingAlreadyFlaggedError,
        simple_problem_builder(status=409, code="CONFLICT", title="Listing is already flagged"),
    )
    mapper.register(
        ListingNotFlaggedError,
        simple_problem_builder(status=409, code="CONFLICT", title="Listing is not flagged"),
    )
    mapper.register(
        StaleListingVersionError,
        simple_problem_builder(
            status=409,
            code="CONFLICT",
            title="Listing was modified by another request (lockVersion mismatch)",
        ),
    )
