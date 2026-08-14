"""QG-06 (Playbook Sec 16): every route actually registered on the app must exist in
contracts/openapi.yaml -- CI fails on drift instead of the two silently diverging (API Sec 13
"drift is a defect"). The converse (a spec operation with no implementation yet) is NOT a
failure here: modules land incrementally, so "not implemented yet" is expected for most of the
spec's operations until each bounded-context task lands its router.

Three categories of registered route are not contract drift and are excluded from the diff:
- FastAPI's own introspection endpoints (/openapi.json, /docs, /docs/oauth2-redirect, /redoc).
- The infra-level liveness/readiness endpoints (/health, /ready) -- sanctioned by the
  Infrastructure & Deployment Architecture document (Sec 6), not part of the `/api/v1` business
  contract, the same way a container orchestrator's own probes always sit outside it.
- /auth/callback/apple -- Apple's own Sign in with Apple wire protocol (a form-urlencoded
  POST + 302 redirect, mandated by Apple whenever any scope is requested), not a JSON operation
  this app defines; it exists purely to hand the authorization code to the real `loginApple`
  JSON operation the same way a webhook receiver sits outside a REST resource contract.
- /payments/payme/webhook, /payments/click/prepare, /payments/click/complete -- ADR-0010's Payme/
  Click server-to-server callbacks: Payme's own JSON-RPC 2.0 envelope and Click's own form-encoded
  Prepare/Complete handshake, neither of which is this app's JSON API (same "webhook receiver
  sits outside the REST resource contract" reasoning as the Apple relay above).

Usage: python tools/check_contract_drift.py contracts/openapi.yaml
"""

from __future__ import annotations

import sys

import yaml
from starlette.routing import Route

NON_CONTRACT_PATHS = {
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/health",
    "/ready",
    "/auth/callback/apple",
    "/payments/payme/webhook",
    "/payments/click/prepare",
    "/payments/click/complete",
}


def _collect_routes(route_list: object, routes: set[tuple[str, str]]) -> None:
    """FastAPI 0.139 wraps each `app.include_router(...)` call in a lazy `_IncludedRouter`
    instead of eagerly flattening its routes into `app.routes` (an internal routing-performance
    change, not a contract change) -- `original_router` is that wrapper's one stable, public-ish
    attribute pointing at the actual `APIRouter` it defers to, so this recurses through it via
    duck typing rather than importing the private `_IncludedRouter` class name, which would
    break if a future FastAPI version renames it."""
    for route in route_list:  # type: ignore[attr-defined]
        nested = getattr(route, "original_router", None)
        if nested is not None:
            _collect_routes(nested.routes, routes)
            continue
        if not isinstance(route, Route):
            continue
        if route.path in NON_CONTRACT_PATHS:
            continue
        for method in route.methods or set():
            if method == "HEAD":
                continue
            routes.add((method, route.path))


def _app_routes() -> set[tuple[str, str]]:
    sys.path.insert(0, "apps/backend/src")
    from main import app  # imported lazily: only needed once main.py exists at all

    routes: set[tuple[str, str]] = set()
    _collect_routes(app.routes, routes)
    return routes


def _spec_routes(openapi_path: str) -> set[tuple[str, str]]:
    with open(openapi_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    routes = set()
    for path, item in spec.get("paths", {}).items():
        for method in item:
            if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                routes.add((method.upper(), path))
    return routes


def main(openapi_path: str) -> int:
    from pathlib import Path

    if not Path("apps/backend/src/main.py").exists():
        print("::notice::QG-06 contract-drift check has no FastAPI app entrypoint yet.")
        return 0

    app_routes = _app_routes()
    spec_routes = _spec_routes(openapi_path)

    undocumented = app_routes - spec_routes
    if undocumented:
        print("QG-06 FAILED: routes registered on the app that aren't in contracts/openapi.yaml:")
        for method, path in sorted(undocumented):
            print(f"  - {method} {path}")
        return 1

    print(
        f"QG-06 OK: {len(app_routes)} registered route(s) all exist in {openapi_path} "
        f"({len(spec_routes)} operation(s) not yet implemented -- expected until each module lands)."
    )
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "contracts/openapi.yaml"
    raise SystemExit(main(path))
