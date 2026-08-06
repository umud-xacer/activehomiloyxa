"""FastAPI router implementing the ONE operation that genuinely belongs to admin
(`getAdminDashboard`) -- every other `Administration`-tagged operation in `contracts/openapi.yaml`
lives on its owning module's own router (`moderation`/`profiles`/`identity`/`billing`/
`analytics`), per `contracts/README.md`'s own P-01 tag-routing rule. Thin translation only: no
business logic lives here."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from admin.application import AdminDashboardUseCases
from admin.interfaces.auth import ActingOperator
from admin.interfaces.di import get_acting_operator, get_dashboard_use_cases
from admin.interfaces.dto import DashboardSummary

admin_router = APIRouter(tags=["Administration"])


@admin_router.get("/admin/dashboard", operation_id="getAdminDashboard")
async def get_admin_dashboard(
    _operator: ActingOperator = Depends(get_acting_operator),
    use_cases: AdminDashboardUseCases = Depends(get_dashboard_use_cases),
) -> DashboardSummary:
    """FR-ADMIN-005. Composed operational KPIs -- every field is a rebuildable projection (or
    honestly null where none is cheaply reachable, see `application/dashboard_use_cases.py`)."""
    summary: dict[str, Any] = await use_cases.get_dashboard()
    return DashboardSummary.model_validate(summary)
