"""analytics.interfaces -- the module's only importable public surface (AIR-02).

STATUS: real DTOs/ports/routers (Task P-15) -- the P-01 marker stubs are now populated. Exposes
NO command surface -- both operations (`queryAuditLog`, `getAdminReports`) are read-only.
"""

from __future__ import annotations

from analytics.interfaces.dto import (
    AuditEntry,
    AuditEntryPage,
)
from analytics.interfaces.ports import (
    AnalyticsQueryPort,
)

__all__ = [
    "AnalyticsQueryPort",
    "AuditEntry",
    "AuditEntryPage",
]
