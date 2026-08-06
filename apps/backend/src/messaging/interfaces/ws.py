"""The WebSocket endpoint definition (Task P-10, DEC-11) -- mounted only by the SEPARATE realtime
gateway app (`apps/backend/src/realtime_main.py`), never by the stateless HTTP tier's own
`main.py`. Shares `get_acting_user`/`get_conversation_use_cases` with the REST routers
(`interfaces/routers.py`) -- FastAPI resolves `Cookie`/`Header`-typed dependency parameters
identically for HTTP and WebSocket routes, so the SAME `get_acting_user` override the composition
root registers for the HTTP tier also authenticates a WebSocket handshake: if it raises, FastAPI
closes the connection before `websocket.accept()` is ever reached -- the upgrade to WSS never
completes for an unauthenticated caller, matching SAD Sec 6's "the realtime tier authenticates
the same session before upgrading to WebSocket" exactly.

No client-to-server application message protocol exists in v1 -- `sendMessage` is a REST-only
operation (`contracts/openapi.yaml` never declares a WS wire format for writes, and inventing one
would be undocumented behaviour). This endpoint is a pure server -> client push channel: it
relays whatever `MessageSubscriberPort.listen` yields (JSON already serialised by
`RealtimePublisherPort.publish_message` on the HTTP tier's own `send_message`/`start_conversation`
calls) and marks each relayed message `delivered_at` via the SAME `ConversationUseCases.
mark_message_delivered` the HTTP tier's use cases module defines -- no business logic is
duplicated between the two runtimes, exactly as DEC-11 requires.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from messaging.application import ConversationUseCases
from messaging.application.ports import MessageSubscriberPort
from messaging.interfaces.auth import ActingUser
from messaging.interfaces.di import (
    get_acting_user,
    get_conversation_use_cases,
    get_message_subscriber,
)

realtime_router = APIRouter()


@realtime_router.websocket("/ws/messaging")
async def messaging_websocket(
    websocket: WebSocket,
    user: ActingUser = Depends(get_acting_user),
    use_cases: ConversationUseCases = Depends(get_conversation_use_cases),
    subscriber: MessageSubscriberPort = Depends(get_message_subscriber),
) -> None:
    await websocket.accept()
    try:
        async for raw in subscriber.listen(user.account_id.value):
            await websocket.send_text(raw)
            await _mark_delivered_best_effort(use_cases, raw)
    except WebSocketDisconnect:
        pass


async def _mark_delivered_best_effort(use_cases: ConversationUseCases, raw: str) -> None:
    """A malformed/unexpected payload must never crash the connection's read loop -- delivery
    tracking is a best-effort side effect of a successful push, not the reason this endpoint
    exists."""
    with contextlib.suppress(Exception):
        payload = json.loads(raw)
        await use_cases.mark_message_delivered(
            UUID(payload["conversationId"]), UUID(payload["messageId"]), now=datetime.now(UTC)
        )
