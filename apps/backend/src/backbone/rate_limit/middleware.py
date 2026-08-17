"""Global per-IP request throttle -- generalizes Security Sec 3.1's brute-force controls to the
WHOLE API surface. Before this, only `identity`'s login/OTP endpoints had any throttling at all;
every other endpoint (search, listings, messaging, and -- most acutely -- `configuration`'s
owner-admin-access slug-guessing oracle, which had zero protection of any kind) could be flooded
without limit. This middleware is a coarse, cheap-to-check backstop against exactly that: a fixed
request-per-IP cap, independent of and in addition to any endpoint's own tighter, purpose-specific
throttle (login lockout, OTP throttle, the owner-admin-access oracle's own lockout).

Pure ASGI middleware, deliberately NOT `BaseHTTPMiddleware` -- same reasoning as
`backbone.errors.middleware.TraceIdMiddleware` (UNF-011, see that class's own docstring): this
needs to send its own 429 response and return without ever calling the downstream app, and
`BaseHTTPMiddleware` re-raises past an already-handled exception on a pooled connection's next
request. Simplest to never route through FastAPI's exception-handling machinery here at all --
the 429 body below is hand-built to the exact same `contracts.errors.Problem` wire shape
(camelCase, `RATE_LIMITED` code) everything else on this API already answers with, so a client
can't tell the difference from a normal `ExceptionMapper`-produced 429.
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from backbone.net import resolve_client_ip
from backbone.rate_limit.tracker import RedisWindowCounter, _RedisCounterClient

logger = logging.getLogger(__name__)

DEFAULT_MAX_REQUESTS = 300
"""Per-IP request budget within `DEFAULT_WINDOW_SECONDS` -- generous enough that no real user or
the frontend's own SSR fetches ever hit it (a full page load is a handful of requests, not
hundreds), but low enough to blunt a scripted flood/scrape run before it does real damage."""

DEFAULT_WINDOW_SECONDS = 60

_EXEMPT_PATHS = frozenset({"/health", "/ready"})
"""Infra Sec 6 liveness/readiness probes -- a load balancer or orchestrator polls these on a
short fixed interval from a small, known set of IPs; throttling them risks a false "unhealthy"
verdict and a bad failover decision, for zero abuse-resistance benefit (they're not attacker
surface)."""


class GlobalRateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        redis: _RedisCounterClient,
        *,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self.app = app
        self._counter = RedisWindowCounter(redis, key_prefix="backbone:rate_limit:global")
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        headers = Headers(raw=scope.get("headers") or [])
        client = scope.get("client")
        ip = resolve_client_ip(headers, fallback_host=client[0] if client else None)

        # Fixed window (`rearm=False`, see `RedisWindowCounter`'s own docstring): a sustained
        # legitimate caller's count resets every `window_seconds` regardless of how continuously
        # it calls, rather than never resetting as long as requests keep arriving.
        #
        # Fail OPEN on a Redis error, not closed: this middleware wraps EVERY request on the
        # site (unlike login/OTP's own lockouts, which only ever touched their own narrow
        # endpoints) -- letting a Redis blip/outage propagate as an unhandled exception here would
        # turn "the rate limiter is briefly unavailable" into "the entire site 500s", a strictly
        # worse outcome than temporarily running unthrottled. Logged so an outage is still visible.
        #
        # Deliberately `Exception`, not just `(RedisError, OSError, TimeoutError)`: a real,
        # reproduced failure mode (redis-py's async connection pool raising a bare
        # `RuntimeError("Event loop is closed")` when reused across two different event loops --
        # never happens in production's one-loop-for-the-process-lifetime uvicorn run, but does in
        # a test suite that spins up more than one `TestClient`/loop against the same imported
        # `app`) is not a `RedisError` subclass and slipped straight through the narrower catch,
        # turning exactly the "whole site 500s" outcome this middleware exists to prevent into a
        # real, observed one (QG-08's `test_logout_without_a_session_is_a_safe_no_op`). This
        # middleware's entire job is best-effort throttling in front of arbitrary downstream
        # routes -- any exception here must degrade to "let the request through unthrottled",
        # never surface as that route's own 500.
        try:
            count = await self._counter.increment(
                ip, window_seconds=self._window_seconds, rearm=False
            )
        except Exception:
            logger.warning("rate_limit.redis_unavailable", extra={"ip": ip}, exc_info=True)
            await self.app(scope, receive, send)
            return

        if count > self._max_requests:
            retry_after = await self._counter.get_retry_after_seconds(ip)
            await _send_too_many_requests(send, retry_after or self._window_seconds)
            return

        await self.app(scope, receive, send)


async def _send_too_many_requests(send: Send, retry_after: int) -> None:
    body = json.dumps(
        {
            "type": "https://errors.activehome.uz/rate-limited",
            "title": "Too many requests",
            "status": 429,
            "code": "RATE_LIMITED",
            "detail": "So'rovlar soni chegaradan oshib ketdi. Birozdan so'ng qayta urinib ko'ring.",
            "traceId": str(uuid4()),
        }
    ).encode("utf-8")
    response_headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("latin-1")),
        (b"retry-after", str(retry_after).encode("latin-1")),
        (b"connection", b"close"),
    ]
    await send({"type": "http.response.start", "status": 429, "headers": response_headers})
    await send({"type": "http.response.body", "body": body})
