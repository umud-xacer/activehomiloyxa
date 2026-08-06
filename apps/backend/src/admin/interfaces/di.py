"""Composition-root OVERRIDE POINTS for admin's router dependencies (mirrors `ads.interfaces.
di`'s own docstring exactly: DIP -- `admin.interfaces` never imports `admin.infrastructure`,
`no-infra-inbound-admin` in `tools/importlinter.cfg`). These functions exist only so
`admin/interfaces/routers.py` has a stable, importable `Depends(...)` target; the real
implementation is registered by the app factory via `app.dependency_overrides[...]`
(`apps/backend/src/composition_root.py`, imported only from `apps/backend/src/main.py`)."""

from __future__ import annotations

from admin.application import AdminDashboardUseCases
from admin.interfaces.auth import ActingOperator


async def get_dashboard_use_cases() -> AdminDashboardUseCases:
    raise NotImplementedError(
        "get_dashboard_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_operator() -> ActingOperator:
    raise NotImplementedError(
        "get_acting_operator was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
