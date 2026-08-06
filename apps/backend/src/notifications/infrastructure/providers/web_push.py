"""VAPID-signed web-push adapter (DEC-18). Implements `notifications.application.ports.
WebPushProviderPort`. `pywebpush`'s own request/response/subscription shapes are confined
entirely to this file -- the port boundary only ever sees `WebPushSubscriptionSnapshot`
(endpoint/p256dh/auth strings) and returns a plain `str`.

NOTE (P-13 "Known gaps", README): no operation anywhere in `contracts/openapi.yaml` registers a
push subscription -- only the `webPush` boolean opt-in exists on `NotificationPreferences`. This
adapter is real and tested against a synthetic subscription; in v1 no code path ever constructs a
real one, since there is no endpoint to submit it (CLAUDE.md: "a missing endpoint is an
architecture decision, not a workaround"). `pywebpush.webpush` is synchronous (uses `requests`);
each send is offloaded to a worker thread so it never blocks the event loop (Playbook Sec 6).
"""

from __future__ import annotations

import asyncio

from pywebpush import webpush

from backbone.persistence.env import required_env
from notifications.application.ports import WebPushSubscriptionSnapshot

_VAPID_SUBJECT = "mailto:support@activehome.uz"
"""Not a secret -- VAPID's own required "sub" claim identifying the sending application."""


class WebPushProviderAdapter:
    def __init__(self) -> None:
        self._private_key = required_env("WEB_PUSH_VAPID_PRIVATE_KEY")

    async def send_push(self, *, subscription: WebPushSubscriptionSnapshot, body: str) -> str:
        await asyncio.to_thread(self._send, subscription, body)
        return subscription.endpoint

    def _send(self, subscription: WebPushSubscriptionSnapshot, body: str) -> None:
        response = webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=body,
            vapid_private_key=self._private_key,
            vapid_claims={"sub": _VAPID_SUBJECT},
            timeout=10.0,
        )
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
