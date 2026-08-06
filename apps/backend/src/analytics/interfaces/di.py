"""Composition-root OVERRIDE POINTS for analytics' router dependencies (mirrors `ads.interfaces.
di`'s own docstring exactly: DIP -- `analytics.interfaces` never imports `analytics.
infrastructure`, `no-infra-inbound-analytics` in `tools/importlinter.cfg`). These functions exist
only so `analytics/interfaces/routers.py` has a stable, importable `Depends(...)` target; the
real implementation is registered by the app factory via `app.dependency_overrides[...]`
(`apps/backend/src/composition_root.py`, imported only from `apps/backend/src/main.py`)."""

from __future__ import annotations

from analytics.application import AuditUseCases, ReportUseCases
from analytics.interfaces.auth import ActingOperator


async def get_audit_use_cases() -> AuditUseCases:
    raise NotImplementedError(
        "get_audit_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_report_use_cases() -> ReportUseCases:
    raise NotImplementedError(
        "get_report_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_audit_acting_operator() -> ActingOperator:
    """Gates `queryAuditLog` (`analytics:audit:read`) -- a distinct permission from
    `getAdminReports`'s, so a distinct DI target, mirroring `profiles.interfaces.di`'s own
    `get_acting_user`/`get_acting_reviewer` split for two permissions in one module."""
    raise NotImplementedError(
        "get_audit_acting_operator was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_reports_acting_operator() -> ActingOperator:
    """Gates `getAdminReports` (`analytics:reports:read`)."""
    raise NotImplementedError(
        "get_reports_acting_operator was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
