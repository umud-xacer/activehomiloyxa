"""Composition-root OVERRIDE POINTS for moderation's router dependencies (mirrors `profiles.
interfaces.di`'s own docstring exactly: DIP -- `moderation.interfaces` never imports
`moderation.infrastructure`, `no-infra-inbound-moderation` tools/importlinter.cfg). These
functions exist only so `moderation/interfaces/routers.py` has a stable, importable `Depends(...)`
target; the real implementation is registered by the app factory via
`app.dependency_overrides[...]` (`apps/backend/src/composition_root.py`, imported only from
`apps/backend/src/main.py`).
"""

from __future__ import annotations

from moderation.application import ModerationUseCases
from moderation.interfaces.auth import ActingModerator


async def get_moderation_use_cases() -> ModerationUseCases:
    raise NotImplementedError(
        "get_moderation_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_moderator() -> ActingModerator:
    raise NotImplementedError(
        "get_acting_moderator was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
