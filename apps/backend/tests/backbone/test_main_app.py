"""apps/backend/src/main.py -- the module-less app skeleton (Infra Sec 6: `/health` liveness,
`/ready` readiness). Uses the real Postgres/Redis fixtures when available; degrades gracefully
(asserts the *shape*, not necessarily 200) when they aren't, since /ready's whole point is to
accurately report an unreachable dependency rather than lying."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "backend" / "src"))


def _client() -> TestClient:
    from main import app

    return TestClient(app)


def test_health_is_always_ok() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_postgres_and_redis_keys() -> None:
    response = _client().get("/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert set(body.keys()) == {"postgres", "redis"}
    assert isinstance(body["postgres"], bool)
    assert isinstance(body["redis"], bool)


def test_ready_status_code_matches_overall_health() -> None:
    response = _client().get("/ready")
    body = response.json()
    expected_status = 200 if all(body.values()) else 503
    assert response.status_code == expected_status


def test_health_and_ready_are_excluded_from_the_contract_drift_surface() -> None:
    """/health and /ready are Infra-sanctioned, not contracts/openapi.yaml operations -- they
    must not silently become "the API contract" by accident."""
    from main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/health" in paths
    assert "/ready" in paths

    import yaml

    openapi_path = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
    with open(openapi_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    assert "/health" not in spec["paths"]
    assert "/ready" not in spec["paths"]
