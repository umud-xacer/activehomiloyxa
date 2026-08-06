"""Composition-root OVERRIDE POINTS for identity's routers (mirrors
`configuration/interfaces/di.py` exactly). No concrete wiring here: `no-infra-inbound-identity`
(tools/importlinter.cfg) forbids `identity.interfaces` from importing `identity.infrastructure`
-- wired at the true composition root instead (DIP). Each function exists only so
`identity/interfaces/routers.py` has a stable, importable `Depends(...)` target; the real
implementation is registered via `app.dependency_overrides[...]` (see
`apps/backend/src/composition_root.py`, imported only from `apps/backend/src/main.py`).
"""

from __future__ import annotations

from identity.application import AccountUseCases, AdminIdentityUseCases, AuthenticationUseCases
from identity.interfaces.auth import ActingOperator, AuthenticatedRequest


async def get_authentication_use_cases() -> AuthenticationUseCases:
    raise NotImplementedError(
        "get_authentication_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_account_use_cases() -> AccountUseCases:
    raise NotImplementedError(
        "get_account_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_admin_identity_use_cases() -> AdminIdentityUseCases:
    raise NotImplementedError(
        "get_admin_identity_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_authenticated_request() -> AuthenticatedRequest:
    raise NotImplementedError(
        "get_authenticated_request was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_users_acting_operator() -> ActingOperator:
    """Gates `adminListUsers`/`adminChangeUserStatus` (`identity:account:manage_status`)."""
    raise NotImplementedError(
        "get_users_acting_operator was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_roles_acting_operator() -> ActingOperator:
    """Gates `assignRole`/`revokeRole` (`identity:role:assign`, ADR-0006)."""
    raise NotImplementedError(
        "get_roles_acting_operator was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_registration_reviewer() -> ActingOperator:
    """Gates `listRegistrationQueue`/`decideRegistration` (`identity:registration:review`,
    ADR-0007)."""
    raise NotImplementedError(
        "get_registration_reviewer was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
