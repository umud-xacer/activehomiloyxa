"""Composition-root OVERRIDE POINTS for messaging's router dependencies (mirrors
`billing.interfaces.di`'s own docstring exactly: DIP -- `messaging.interfaces` never imports
`messaging.infrastructure`, `no-infra-inbound-messaging` tools/importlinter.cfg). These functions
exist only so `messaging/interfaces/routers.py` (and `messaging/interfaces/ws.py`, shared by the
realtime runner) has a stable, importable `Depends(...)` target; the real implementation is
registered by each runtime's own app factory via `app.dependency_overrides[...]`."""

from __future__ import annotations

from messaging.application import BlockUseCases, ConversationUseCases, ReportUseCases
from messaging.application.ports import MessageSubscriberPort
from messaging.interfaces.auth import ActingUser


async def get_conversation_use_cases() -> ConversationUseCases:
    raise NotImplementedError(
        "get_conversation_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_block_use_cases() -> BlockUseCases:
    raise NotImplementedError(
        "get_block_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_report_use_cases() -> ReportUseCases:
    raise NotImplementedError(
        "get_report_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_user() -> ActingUser:
    raise NotImplementedError(
        "get_acting_user was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_message_subscriber() -> MessageSubscriberPort:
    """Overridden only by the realtime gateway's own app factory (`realtime_main.py`) -- the
    stateless HTTP tier never overrides this (`interfaces/routers.py` has no dependency on it)."""
    raise NotImplementedError(
        "get_message_subscriber was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
