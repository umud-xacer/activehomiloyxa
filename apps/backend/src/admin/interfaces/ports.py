"""admin -- ports (Task P-01). Abstract surface only (typing.Protocol): no implementation.
`admin` is a thin composition context (SAD Sec 7.2) -- it owns no marketplace aggregate, so
almost everything under the `Administration` OpenAPI tag actually belongs to the module that
owns the underlying aggregate (billing invoices -> billing, moderation queue -> moderation,
user status -> identity, verification queue -> profiles, audit/reports -> analytics -- see each
of those modules' ports.py). Only the dashboard composition endpoint, which does not map to a
single owning aggregate, is modelled here.
"""

from __future__ import annotations

from typing import Protocol

from admin.interfaces.dto import DashboardSummary


class AdminCompositionPort(Protocol):
    """Derived from OpenAPI operations: `getAdminDashboard`."""

    async def get_admin_dashboard(self) -> DashboardSummary:
        """`GET /admin/dashboard` (operationId `getAdminDashboard`). Get admin dashboard summary."""
        ...
