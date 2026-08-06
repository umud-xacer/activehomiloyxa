"""Registers ads' typed domain/application exceptions onto the shared
`backbone.errors.ExceptionMapper` (the same registry `billing.interfaces.errors`/`catalog.
interfaces.errors` extend). Called once from the composition root (`apps/backend/src/main.py`).

Status/code choices follow `contracts/errors/problem.py`'s closed `ErrorCode` vocabulary and
ADR-0004's own decision that no new `ErrorCode` member is needed: I-21/I-20 gate failures are
`BUSINESS_RULE_VIOLATION` (422, mirroring `scheduleCampaign`'s own declared response set), an
illegal lifecycle transition attempt is `ILLEGAL_STATE_TRANSITION` (409).
"""

from __future__ import annotations

from ads.application.exceptions import (
    CampaignNotFoundError,
    EntitlementNotFoundError,
    SlotNotFoundError,
)
from ads.domain import (
    CampaignNotEligibleError,
    IllegalCampaignStateTransitionError,
    InvalidScheduleError,
)
from backbone.errors import ExceptionMapper, simple_problem_builder


def register_ads_exception_mappings(mapper: ExceptionMapper) -> None:
    # --- validation (422) -----------------------------------------------------------------------
    mapper.register(
        InvalidScheduleError,
        simple_problem_builder(status=422, code="VALIDATION_FAILED", title="Invalid schedule"),
    )
    mapper.register(
        CampaignNotEligibleError,
        simple_problem_builder(
            status=422,
            code="BUSINESS_RULE_VIOLATION",
            title="Campaign is not eligible to serve (I-21/I-20)",
        ),
    )

    # --- not found (404) -------------------------------------------------------------------------
    mapper.register(
        CampaignNotFoundError,
        simple_problem_builder(status=404, code="RESOURCE_NOT_FOUND", title="Campaign not found"),
    )
    mapper.register(
        SlotNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Placement slot not found"
        ),
    )
    mapper.register(
        EntitlementNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Entitlement not found"
        ),
    )

    # --- conflict (409) -------------------------------------------------------------------------
    mapper.register(
        IllegalCampaignStateTransitionError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Campaign cannot make that transition",
        ),
    )
