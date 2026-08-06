"""FastAPI router implementing exactly the 3 moderation-tagged OpenAPI operations P-12 builds
(`contracts/openapi.yaml`, tag `Administration`): `listModerationQueue`, `getModerationCase`,
`applyModerationAction`. Thin translation only: query/path/body -> use case call -> domain object
-> already-frozen `interfaces/dto.py` DTO. All business logic lives in `application`/`domain`;
this module owns none. Report intake (`createReport`) is messaging's own operation (Task P-10) --
moderation only consumes the resulting `ContentReported` event
(`infrastructure/event_projection.py::handle_content_reported`), so no router method exists here
for it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from moderation.application import ModerationUseCases
from moderation.domain import (
    CaseStatus,
    ResolutionAction,
    SubjectType,
)
from moderation.domain import (
    ModerationCase as ModerationCaseAggregate,
)
from moderation.interfaces.auth import ActingModerator
from moderation.interfaces.di import get_acting_moderator, get_moderation_use_cases
from moderation.interfaces.dto import (
    ModerationActionRequest,
    ModerationCasePage,
    PageInfo,
)
from moderation.interfaces.dto import (
    ModerationCase as ModerationCaseDto,
)

admin_moderation_router = APIRouter(tags=["Administration"])


def _clamp_limit(limit: int | None) -> int:
    return min(max(limit or 20, 1), 100)


def _to_case_dto(case: ModerationCaseAggregate) -> ModerationCaseDto:
    return ModerationCaseDto(
        id=case.id,
        subject_type=case.subject.subject_type.value,
        subject_id=case.subject.subject_id,
        origin_type=case.origin.origin_type.value,
        report_reason=case.origin.report_reason,
        rule_key=case.origin.rule_key,
        status=case.status.value,
        resolution_action=case.resolution.action.value if case.resolution else None,
        created_at=case.created_at,
    )


@admin_moderation_router.get("/admin/moderation-queue", operation_id="listModerationQueue")
async def list_moderation_queue(
    status: Literal["OPEN", "IN_REVIEW", "RESOLVED"] | None = None,
    subjectType: Literal["LISTING", "CONVERSATION", "USER", "PROFILE"] | None = None,
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    _moderator: ActingModerator = Depends(get_acting_moderator),
    use_cases: ModerationUseCases = Depends(get_moderation_use_cases),
) -> ModerationCasePage:
    page_limit = _clamp_limit(limit)
    cases, next_cursor = await use_cases.list_queue(
        status=CaseStatus(status) if status else None,
        subject_type=SubjectType(subjectType) if subjectType else None,
        cursor=cursor,
        limit=page_limit,
    )
    return ModerationCasePage(
        items=[_to_case_dto(case) for case in cases],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


@admin_moderation_router.get("/admin/moderation-queue/{caseId}", operation_id="getModerationCase")
async def get_moderation_case(
    caseId: UUID,
    _moderator: ActingModerator = Depends(get_acting_moderator),
    use_cases: ModerationUseCases = Depends(get_moderation_use_cases),
) -> ModerationCaseDto:
    case = await use_cases.get_case(caseId)
    return _to_case_dto(case)


@admin_moderation_router.post(
    "/admin/moderation-queue/{caseId}/action", operation_id="applyModerationAction"
)
async def apply_moderation_action(
    caseId: UUID,
    body: ModerationActionRequest,
    moderator: ActingModerator = Depends(get_acting_moderator),
    use_cases: ModerationUseCases = Depends(get_moderation_use_cases),
) -> ModerationCaseDto:
    case = await use_cases.resolve_case(
        caseId,
        action=ResolutionAction(body.action),
        note=body.note,
        moderator_user_id=moderator.account_id.value,
        now=datetime.now(UTC),
    )
    return _to_case_dto(case)
