"""FastAPI router implementing exactly the two operations `contracts/README.md`'s own tag-
routing rule assigns to analytics (both frozen under the cross-cutting `Administration` tag
since Task P-01, routed here because analytics owns the underlying data --
`queryAuditLog`/`getAdminReports`). Thin translation only: query params -> use case call ->
already-frozen `interfaces/dto.py` DTO / plain dict. All business logic lives in
`application`/`domain`; this module owns none. Exposes NO command surface -- analytics is a pure
sink (SAD Sec 8: "shared_kernel (event sink)").
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from analytics.application import AuditUseCases, ReportUseCases
from analytics.interfaces.auth import ActingOperator
from analytics.interfaces.di import (
    get_audit_acting_operator,
    get_audit_use_cases,
    get_report_use_cases,
    get_reports_acting_operator,
)
from analytics.interfaces.dto import AuditEntry, AuditEntryPage, PageInfo

analytics_router = APIRouter(tags=["Administration"])


def _clamp_limit(limit: int | None) -> int:
    return min(max(limit or 20, 1), 100)


def _date_to_datetime(value: date | None, *, end_of_day: bool) -> datetime | None:
    if value is None:
        return None
    if end_of_day:
        return datetime(value.year, value.month, value.day, 23, 59, 59, 999999, tzinfo=UTC)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


@analytics_router.get("/admin/audit-log", operation_id="queryAuditLog")
async def query_audit_log(
    actorUserId: UUID | None = None,
    targetType: str | None = None,
    action: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    cursor: str | None = None,
    limit: int | None = 20,
    _operator: ActingOperator = Depends(get_audit_acting_operator),
    use_cases: AuditUseCases = Depends(get_audit_use_cases),
) -> AuditEntryPage:
    """FR-AUDIT-002. Read-only -- audit entries are never mutated or deleted."""
    entries, next_cursor = await use_cases.query_audit_log(
        actor_user_id=actorUserId,
        target_type=targetType,
        action=action,
        occurred_from=from_,
        occurred_to=to,
        cursor=cursor,
        limit=_clamp_limit(limit),
    )
    return AuditEntryPage(
        items=[
            AuditEntry(
                id=entry.id,
                actor_user_id=entry.actor_user_id.value if entry.actor_user_id else None,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                payload=entry.payload,
                occurred_at=entry.occurred_at,
            )
            for entry in entries
        ],
        page=PageInfo(limit=_clamp_limit(limit), next_cursor=next_cursor),
    )


@analytics_router.get("/admin/reports", operation_id="getAdminReports")
async def get_admin_reports(
    report: str = Query(...),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    _operator: ActingOperator = Depends(get_reports_acting_operator),
    use_cases: ReportUseCases = Depends(get_report_use_cases),
) -> dict[str, Any]:
    """FR-ADMIN-005. Rebuildable projections -- every field returned is recomputed from
    analytics' own two fact streams, never a second source of truth."""
    return await use_cases.get_admin_reports(
        report=report,
        occurred_from=_date_to_datetime(from_, end_of_day=False),
        occurred_to=_date_to_datetime(to, end_of_day=True),
    )
