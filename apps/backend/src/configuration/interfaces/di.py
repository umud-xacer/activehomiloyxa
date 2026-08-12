"""Composition-root OVERRIDE POINTS for the configuration router's use-case dependencies.

Deliberately contains no concrete wiring: `no-infra-inbound-configuration` (tools/importlinter.cfg,
DIP) forbids `configuration.interfaces` from importing `configuration.infrastructure` (or the
SQLAlchemy/Redis/outbox types that sit behind it) -- infrastructure is wired at the true
composition root, never statically imported by a module's own interfaces/application/domain.
These two functions exist only so `configuration/interfaces/routers.py` has a stable, importable
`Depends(...)` target; the real implementation is registered by the app factory via
`app.dependency_overrides[get_configuration_use_cases] = <real provider>` (see
`apps/backend/src/composition_root.py`, imported only from `apps/backend/src/main.py`).
"""

from __future__ import annotations

from configuration.application import (
    CategoryReadUseCases,
    ConfigurationUseCases,
    OwnerAdminLockoutPort,
)


async def get_configuration_use_cases() -> ConfigurationUseCases:
    raise NotImplementedError(
        "get_configuration_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_category_read_use_cases() -> CategoryReadUseCases:
    raise NotImplementedError(
        "get_category_read_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_owner_admin_lockout_counter() -> OwnerAdminLockoutPort:
    raise NotImplementedError(
        "get_owner_admin_lockout_counter was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
