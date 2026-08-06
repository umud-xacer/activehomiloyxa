"""Composition-root OVERRIDE POINTS for notifications' router dependencies (mirrors `moderation.
interfaces.di`'s own docstring exactly: DIP -- `notifications.interfaces` never imports
`notifications.infrastructure`, `no-infra-inbound-notifications` tools/importlinter.cfg). These
functions exist only so `notifications/interfaces/routers.py` has a stable, importable
`Depends(...)` target; the real implementation is registered by the app factory via
`app.dependency_overrides[...]` (`apps/backend/src/composition_root.py`, imported only from
`apps/backend/src/main.py`).
"""

from __future__ import annotations

from notifications.application import NotificationUseCases
from notifications.interfaces.auth import ActingUser


async def get_notification_use_cases() -> NotificationUseCases:
    raise NotImplementedError(
        "get_notification_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_user() -> ActingUser:
    raise NotImplementedError(
        "get_acting_user was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
