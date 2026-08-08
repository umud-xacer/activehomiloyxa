"""Wires `ExceptionMapper` into a FastAPI app (Playbook Sec 6: "never leak stack traces to
clients; never swallow exceptions silently... correlate via traceId"). Every response this
produces is `contracts.errors.Problem`, alias-serialised to the frozen wire shape.

Trace-id correlation: reads `X-Request-Id` if the edge/client supplied one, else mints a fresh
one -- either way it's on `request.state.trace_id` for the logging config to pick up too, and
echoed back on the response so a client can correlate its own logs with a server-side incident.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backbone.errors.mapping import (
    ExceptionMapper,
    default_exception_mapper,
    simple_problem_builder,
)
from contracts.errors import Problem

logger = logging.getLogger("backbone.errors")

TRACE_ID_HEADER = "X-Request-Id"
_TRACE_ID_HEADER_BYTES = TRACE_ID_HEADER.encode("latin-1")


class TraceIdMiddleware:
    """Pure ASGI middleware, deliberately NOT `BaseHTTPMiddleware` (UNF-011). `BaseHTTPMiddleware`
    runs the downstream app in a separate task and re-raises its exception from `call_next()` even
    once an app-level `@app.exception_handler` has already resolved it and sent a response --
    confirmed by reproducing the exact reported symptom (a pooled client alternating
    `401`/`ReadError` against `GET /me` with no cookie): the first request's `InvalidSessionTokenError`
    is caught by `install_error_handlers`'s catch-all and correctly answered 401, but
    `call_next()` still re-raises it past this middleware's own (uncaught) `dispatch()`, which
    uvicorn has no choice but to answer by resetting the connection -- corrupting it for
    whichever request reuses it next. Every `ExceptionMapper`-produced status (401/403/404/409)
    hit this; 2xx never does (no exception involved), and FastAPI's own built-in
    `RequestValidationError`/422 handling doesn't either (resolved deeper in routing, never
    reaching `call_next`'s re-raise path). Plain ASGI middleware only ever touches the `send`
    callable, so there is no second exception-propagation path to race against."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        trace_id = headers.get(TRACE_ID_HEADER.lower().encode("latin-1"))
        trace_id_str = trace_id.decode("latin-1") if trace_id else str(uuid4())
        scope.setdefault("state", {})["trace_id"] = trace_id_str

        async def send_with_trace_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        (_TRACE_ID_HEADER_BYTES, trace_id_str.encode("latin-1")),
                    ],
                }
            await send(message)

        await self.app(scope, receive, send_with_trace_id)


def _problem_response(problem: Problem, trace_id: str, *, exc: Exception | None = None) -> JSONResponse:
    headers = {TRACE_ID_HEADER: trace_id, "Connection": "close"}
    # `retry_after_seconds` is a duck-typed convention, not a `ProblemBuilder`/`Problem` contract
    # field: every 429-mapped exception that carries a wait time already exposes it as a plain
    # attribute (`OtpThrottledError`, `LoginLockedOutError`, `messaging.RateLimitExceededError`),
    # so reading it here generically closes `contracts/openapi.yaml`'s `TooManyRequests` response
    # component's own declared-but-previously-never-populated `Retry-After` header for all three
    # at once, without widening `ProblemBuilder`'s signature or touching `ExceptionMapper` at all.
    retry_after = getattr(exc, "retry_after_seconds", None) if exc is not None else None
    if isinstance(retry_after, int):
        headers["Retry-After"] = str(retry_after)
    with_trace_id = problem.model_copy(update={"trace_id": trace_id})
    return JSONResponse(
        status_code=with_trace_id.status,
        content=with_trace_id.model_dump(by_alias=True, mode="json", exclude_none=True),
        # UNF-011: reproduced against a bare FastAPI/Starlette 1.3.1/uvicorn 0.51.0 app with
        # zero project code -- any response reached via `@app.exception_handler`, on a
        # keep-alive connection's SECOND-and-later request, has its own already-handled
        # exception re-raised past `wrap_app_handling_exceptions` (`conn.scope["starlette.
        # exception_handlers"]` lookup fails), reaching uvicorn uncaught and forcing a
        # connection reset -- so any pooled client (including the frontend's own server-side
        # fetch) that reuses a connection across an error response gets `ReadError`/`Connection
        # reset by peer` on the NEXT request over it, with no error surfaced to the caller of
        # THIS response (Problem is delivered fine; it's the connection's next tenant that
        # pays for it). Closing the connection after every mapped error sidesteps it
        # entirely -- confirmed fixed against the same bare repro -- rather than chasing further
        # into Starlette internals for a root cause with no newer pinned-dependency version to
        # try (`starlette`/`uvicorn` are already at their latest release).
        headers=headers,
    )


def install_error_handlers(app: FastAPI, mapper: ExceptionMapper | None = None) -> None:
    """Call once, in the app factory, after `TraceIdMiddleware` is added -- the handlers below
    read `request.state.trace_id`, which only exists once that middleware has run."""
    mapper = mapper or default_exception_mapper()

    unhandled_fallback = simple_problem_builder(
        status=500,
        code="DEPENDENCY_DEGRADED",
        title="Internal server error",
        detail=None,  # never the real exception message -- it may carry internals (Playbook Sec 6)
    )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # `default_exception_mapper()` always registers `RequestValidationError`, but `mapper`
        # is an injectable parameter -- a caller could pass one that doesn't. Falling back to
        # the same well-formed-500 builder `handle_unhandled_exception` uses keeps this handler's
        # own guarantee ("every response is a `Problem`, Playbook Sec 6") true even then, rather
        # than crashing on an unmet assertion (or, stripped under `-O`, on `None.model_copy`).
        problem = mapper.resolve(exc) or unhandled_fallback(exc)
        return _problem_response(problem, _trace_id(request), exc=exc)

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _trace_id(request)
        logger.exception(
            "unhandled exception",
            extra={"trace_id": trace_id, "path": request.url.path, "method": request.method},
        )
        problem = mapper.resolve(exc) or unhandled_fallback(exc)
        return _problem_response(problem, trace_id, exc=exc)


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", None) or str(uuid4())
