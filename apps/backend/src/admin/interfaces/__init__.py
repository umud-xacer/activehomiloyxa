"""admin.interfaces -- the module's only importable public surface (AIR-02).

STATUS: real DTO/port/router (Task P-16) -- the P-01 marker stub is now populated. Exposes
exactly one operation (`getAdminDashboard`) -- every other `Administration`-tagged operation
lives on its owning module's own router (see `admin/README.md`)."""

from __future__ import annotations

from admin.interfaces.dto import DashboardSummary
from admin.interfaces.ports import AdminCompositionPort

__all__ = [
    "AdminCompositionPort",
    "DashboardSummary",
]
