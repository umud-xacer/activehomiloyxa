"""analytics -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from analytics.interfaces.dto import (
    AuditEntryPage,
)


class AnalyticsQueryPort(Protocol):
    """Derived from OpenAPI operations: `getAdminReports`, `queryAuditLog`."""

    async def get_admin_reports(
        self,
        report: Literal[
            "LISTINGS_OVERVIEW",
            "USER_GROWTH",
            "REVENUE",
            "VERIFICATION_SLA",
            "MODERATION_THROUGHPUT",
        ],
        from_: str | None = None,
        to: str | None = None,
    ) -> dict[str, Any]:
        """`GET /admin/reports` (operationId `getAdminReports`). Operational reports"""
        ...

    async def query_audit_log(
        self,
        actor_user_id: UUID | None = None,
        target_type: str | None = None,
        action: str | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
        cursor: str | None = None,
        limit: int | None = 20,
    ) -> AuditEntryPage:
        """`GET /admin/audit-log` (operationId `queryAuditLog`). Query the audit log"""
        ...
