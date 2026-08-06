"""Registers media's typed domain/application exceptions onto the shared
`backbone.errors.ExceptionMapper` (the same registry `identity.interfaces.errors` extends).
Called once from the composition root (`apps/backend/src/main.py`).

Status/code choices follow `contracts/errors/problem.py`'s closed `ErrorCode` vocabulary.
`UnsupportedMediaTypeError`/`OversizeMediaError` share one code -- `contracts/openapi.yaml`'s
`initMediaUpload` 422 response covers both under "Unsupported media type or oversize" without a
separate code for each (see the exceptions' own docstrings in `media/domain/exceptions.py`).
`ScanNotCleanError`/`IllegalAssetStateTransitionError`/`VariantNotFoundError` are not reachable
from any of the three routed operations today (they only fire inside the worker's own state
machine) -- registered anyway for completeness/defence-in-depth, the same discipline
`identity.interfaces.errors` already applies to its own internally-triggered exceptions.
"""

from __future__ import annotations

from backbone.errors import ExceptionMapper, simple_problem_builder
from media.application.exceptions import MediaAssetNotFoundError, NotAssetOwnerError
from media.domain import (
    AssetNotDeliverableError,
    IllegalAssetStateTransitionError,
    OversizeMediaError,
    ScanNotCleanError,
    UnsupportedMediaTypeError,
    VariantNotFoundError,
)


def register_media_exception_mappings(mapper: ExceptionMapper) -> None:
    # --- validation (422) ---------------------------------------------------------------------
    mapper.register(
        UnsupportedMediaTypeError,
        simple_problem_builder(
            status=422,
            code="UNSUPPORTED_MEDIA_TYPE",
            title="Content type is not an accepted image type",
        ),
    )
    mapper.register(
        OversizeMediaError,
        simple_problem_builder(
            status=422, code="UNSUPPORTED_MEDIA_TYPE", title="Image exceeds the maximum upload size"
        ),
    )

    # --- authorization (403) --------------------------------------------------------------------
    mapper.register(
        NotAssetOwnerError,
        simple_problem_builder(
            status=403, code="PERMISSION_DENIED", title="Caller does not own this media asset"
        ),
    )

    # --- not found (404) -----------------------------------------------------------------------
    mapper.register(
        MediaAssetNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Media asset not found"
        ),
    )
    mapper.register(
        VariantNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="No such image variant"
        ),
    )

    # --- conflict (409) ------------------------------------------------------------------------
    mapper.register(
        IllegalAssetStateTransitionError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Media asset cannot make that transition",
        ),
    )
    mapper.register(
        ScanNotCleanError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Media asset cannot be processed before its scan is clean",
        ),
    )
    mapper.register(
        AssetNotDeliverableError,
        simple_problem_builder(
            status=409, code="CONFLICT", title="Media asset is not yet available for delivery"
        ),
    )
