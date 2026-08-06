"""ExceptionMapper + the FastAPI error-envelope middleware (API contract: one Problem-style
envelope; Playbook Sec 6: never leak stack traces, never swallow exceptions silently)."""

from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

from backbone.errors import (
    TraceIdMiddleware,
    default_exception_mapper,
    install_error_handlers,
    simple_problem_builder,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/needs-int")
    async def needs_int(n: int = Query(...)) -> dict[str, int]:
        return {"n": n}

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("sensitive internal detail: db password is hunter2")

    class QuotaExceededError(Exception):
        pass

    @app.get("/quota")
    async def quota() -> None:
        raise QuotaExceededError

    # a later task's module registers its own typed exceptions onto the same default mapper
    # this way, rather than building a second mapping mechanism.
    mapper = default_exception_mapper()
    mapper.register(
        QuotaExceededError,
        simple_problem_builder(status=409, code="QUOTA_EXCEEDED", title="Quota exceeded"),
    )
    install_error_handlers(app, mapper)

    return app


def test_FR_ERR_001_validation_error_returns_problem_with_field_details() -> None:
    client = TestClient(_make_app())
    response = client.get("/needs-int", params={"n": "not-an-int"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["status"] == 422
    assert body["errors"][0]["path"] == "/query/n"
    assert "traceId" in body


def test_FR_ERR_002_unhandled_exception_never_leaks_detail() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "DEPENDENCY_DEGRADED"
    assert "hunter2" not in response.text
    assert "sensitive internal detail" not in response.text
    assert "traceId" in body


def test_registered_domain_exception_maps_to_its_own_status_and_code() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=False)
    response = client.get("/quota")
    assert response.status_code == 409
    assert response.json()["code"] == "QUOTA_EXCEEDED"


def test_trace_id_is_echoed_on_the_response_header() -> None:
    client = TestClient(_make_app())
    response = client.get("/needs-int", params={"n": 1}, headers={"X-Request-Id": "trace-abc"})
    assert response.headers["x-request-id"] == "trace-abc"


def test_trace_id_is_generated_when_absent() -> None:
    client = TestClient(_make_app())
    response = client.get("/needs-int", params={"n": 1})
    assert response.headers["x-request-id"]


def test_error_body_trace_id_matches_response_header() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=False)
    response = client.get("/boom", headers={"X-Request-Id": "trace-xyz"})
    assert response.json()["traceId"] == "trace-xyz"
    assert response.headers["x-request-id"] == "trace-xyz"


def test_UNF_011_mapped_error_responses_close_the_connection() -> None:
    """UNF-011: reproduced against a bare FastAPI/Starlette/uvicorn app with none of this
    project's code -- any `@app.exception_handler`-produced response, on a keep-alive
    connection's second-and-later request, has its own already-handled exception re-raised past
    Starlette's own exception-handling wrapper and reaches uvicorn uncaught, which has no choice
    but to reset the connection. `TestClient` doesn't open a real socket, so it can't reproduce
    the crash itself, but it can assert the actual fix: every mapped error tells the client (and
    any proxy) to close the connection rather than let it be reused into that trap. 2xx responses
    are unaffected -- no exception is ever involved on that path, and the header would be an
    unnecessary connection churn for the overwhelming majority of traffic."""
    client = TestClient(_make_app(), raise_server_exceptions=False)

    for path, params in (("/boom", None), ("/quota", None), ("/needs-int", {"n": "nope"})):
        response = client.get(path, params=params)
        assert response.headers["connection"] == "close", path

    ok_response = client.get("/needs-int", params={"n": 1})
    assert "connection" not in {h.lower() for h in ok_response.headers}
