"""The realtime gateway entrypoint (Task P-10, DEC-11; Infra Sec 6's `realtime` container: "GET
/health; WS ping"). A SEPARATE FastAPI app/process from `main.py`'s stateless HTTP tier -- holds
WebSocket connections and Redis pub/sub subscriptions (stateful), which the HTTP tier must never
do (SAD Sec 6). Mounts only `messaging.interfaces.ws.realtime_router` -- no REST business
endpoints, no other module's router. Shares the SAME `messaging.application`/`messaging.domain`
layers as `main.py`'s own `messaging_router` (via the composition root's `provide_conversation_
use_cases`) -- neither runtime duplicates messaging's business logic.

Run: uvicorn realtime_main:app (from apps/backend/src, matching how `main.py`'s own `app` is
served) -- see `deployment/compose/docker-compose.yml`'s `realtime` service.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as redis_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

import composition_root
from backbone.errors import default_exception_mapper, install_error_handlers
from backbone.logging import configure_logging
from backbone.persistence.engine import MissingDatabaseConfigError, make_engine
from backbone.persistence.redis_client import redis_url
from messaging.interfaces.di import (
    get_acting_user,
    get_conversation_use_cases,
    get_message_subscriber,
)
from messaging.interfaces.errors import register_messaging_exception_mappings
from messaging.interfaces.ws import realtime_router


def create_realtime_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Active Home Platform Realtime Gateway")

    mapper = default_exception_mapper()
    register_messaging_exception_mappings(mapper)
    install_error_handlers(app, mapper)

    app.dependency_overrides[get_acting_user] = composition_root.provide_messaging_acting_user
    app.dependency_overrides[get_conversation_use_cases] = (
        composition_root.provide_conversation_use_cases
    )
    app.dependency_overrides[get_message_subscriber] = composition_root.provide_message_subscriber

    app.include_router(realtime_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness only -- the process is up. No dependency checks (Infra Sec 6)."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        """Readiness -- PostgreSQL and Redis both reachable, mirrors `main.py`'s own `/ready`
        exactly (Infra Sec 6). Redis matters even more here than for the HTTP tier: it is this
        process's own pub/sub bus, not just a cache."""
        checks: dict[str, bool] = {}

        try:
            engine = make_engine()
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                checks["postgres"] = True
            finally:
                await engine.dispose()
        except (MissingDatabaseConfigError, OSError, TimeoutError):
            checks["postgres"] = False

        try:
            client = redis_asyncio.from_url(redis_url())
            try:
                await asyncio.wait_for(client.ping(), timeout=3.0)
                checks["redis"] = True
            finally:
                await client.aclose()
        except (MissingDatabaseConfigError, OSError, TimeoutError):
            checks["redis"] = False

        healthy = all(checks.values())
        return JSONResponse(status_code=200 if healthy else 503, content=checks)

    return app


app = create_realtime_app()
