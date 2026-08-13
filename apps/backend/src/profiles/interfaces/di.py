"""Composition-root OVERRIDE POINTS for profiles' router dependencies (mirrors `billing.
interfaces.di`'s own docstring exactly: DIP -- `profiles.interfaces` never imports
`profiles.infrastructure`, `no-infra-inbound-profiles` tools/importlinter.cfg). These functions
exist only so `profiles/interfaces/routers.py` has a stable, importable `Depends(...)` target;
the real implementation is registered by the app factory via `app.dependency_overrides[...]`
(`apps/backend/src/composition_root.py`, imported only from `apps/backend/src/main.py`).
"""

from __future__ import annotations

from profiles.application import ProfileUseCases, VerificationUseCases
from profiles.interfaces.auth import ActingProfileManager, ActingReviewer, ActingUser


async def get_profile_use_cases() -> ProfileUseCases:
    raise NotImplementedError(
        "get_profile_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_verification_use_cases() -> VerificationUseCases:
    raise NotImplementedError(
        "get_verification_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_user() -> ActingUser:
    raise NotImplementedError(
        "get_acting_user was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_reviewer() -> ActingReviewer:
    raise NotImplementedError(
        "get_acting_reviewer was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_profile_manager() -> ActingProfileManager:
    raise NotImplementedError(
        "get_acting_profile_manager was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
