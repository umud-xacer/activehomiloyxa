"""Composition-root OVERRIDE POINTS for media's router dependencies.

Deliberately contains no concrete wiring: `no-infra-inbound-media` (tools/importlinter.cfg,
DIP) forbids `media.interfaces` from importing `media.infrastructure` (or the SQLAlchemy/boto3/
Pillow types that sit behind it) -- infrastructure is wired at the true composition root, never
statically imported by a module's own interfaces/application/domain. These two functions exist
only so `media/interfaces/routers.py` has a stable, importable `Depends(...)` target; the real
implementation is registered by the app factory via `app.dependency_overrides[...]` (see
`apps/backend/src/composition_root.py`, imported only from `apps/backend/src/main.py`).
"""

from __future__ import annotations

from media.application import MediaIntakeUseCases
from media.interfaces.auth import ActingUser


async def get_media_intake_use_cases() -> MediaIntakeUseCases:
    raise NotImplementedError(
        "get_media_intake_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_user() -> ActingUser:
    raise NotImplementedError(
        "get_acting_user was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
