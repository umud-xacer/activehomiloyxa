"""QG-08 / P-20 validation checklist: "the consolidated authorization matrix ... is GREEN;
default-deny holds everywhere including /admin." Runs against the REAL, fully-wired
`main.create_app()` -- the real `composition_root` providers, not fakes -- so this is a genuine
proof about the deployed app, not about a test double standing in for it. Needs real
PostgreSQL/Redis (every `provide_*_acting_user`/`provide_*_acting_operator` still constructs its
real session-factory dependencies even though the auth check itself short-circuits before ever
querying them for a request with no session cookie/bearer token at all).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from tests.authorization.no_route_grants_access import (
    SecuredOperation,
    resolved_path,
    secured_operations,
)
from tests.e2e.conftest import _DEFAULT_ENV

pytestmark = pytest.mark.integration

POSTGRES_AVAILABLE = bool(os.environ.get("POSTGRES_HOST"))

_INTENTIONALLY_IDEMPOTENT_WITHOUT_A_SESSION = {"logout"}
"""`POST /auth/logout` (`identity/interfaces/routers.py::logout`) is tagged as a secured operation
in the frozen contract, but its real implementation is a deliberate no-op when no session/bearer
token is present at all (`if raw_token is not None: await use_cases.logout(...)`, then
unconditionally `204`) -- the same idempotent-DELETE idiom most REST APIs use: "ensure I am logged
out" trivially holds if you were never logged in, and it discloses/mutates nothing. The blanket
"every secured operation must reject a sessionless caller" assumption below is correct for every
OTHER operation but not this one by design, so it is swept separately by
`test_logout_without_a_session_is_a_safe_no_op` instead of asserted here. (P-20 finding: before
this exclusion existed, this test passed for `logout` anyway, but for an unrelated, accidental
reason -- `ESKIZ_API_BASE_URL` was never set anywhere in the test environment, so constructing
`get_authentication_use_cases`'s real Eskiz-backed dependency itself raised `MissingInfraConfig
Error` -> 500, before the handler's own, correctly-permissive logic was ever reached.)"""
_SECURED_OPERATIONS = [
    op for op in secured_operations() if op.id not in _INTENTIONALLY_IDEMPOTENT_WITHOUT_A_SESSION
]


@pytest.fixture(autouse=True)
def _skip_without_datastores() -> None:
    if not POSTGRES_AVAILABLE:
        pytest.skip("POSTGRES_HOST not set -- no real Postgres/Redis to test the real app against")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def test_at_least_the_documented_public_operations_exist() -> None:
    """Sanity check on the harness itself: the public/secured split in `contracts/openapi.yaml`
    isn't accidentally empty or inverted (e.g. every operation reading `security: []`)."""
    assert len(_SECURED_OPERATIONS) >= 80, (
        f"expected roughly 88 secured operations, found {len(_SECURED_OPERATIONS)} -- "
        "the security: [] parsing in no_route_grants_access.py may be broken"
    )


@pytest.mark.parametrize(
    "operation",
    _SECURED_OPERATIONS,
    ids=[op.id for op in _SECURED_OPERATIONS],
)
def test_no_secured_operation_succeeds_without_a_session(
    client: TestClient, operation: SecuredOperation
) -> None:
    path = "/api/v1" + resolved_path(operation)
    kwargs: dict[str, object] = {}
    if operation.has_body:
        kwargs["json"] = {}
    response = client.request(operation.verb, path, **kwargs)  # type: ignore[arg-type]
    assert response.status_code < 200 or response.status_code >= 300, (
        f"{operation.id} ({operation.verb} {path}) succeeded with no session/bearer "
        f"token at all -- status {response.status_code}, body {response.text[:500]}"
    )


def test_logout_without_a_session_is_a_safe_no_op(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one documented exception (see `_INTENTIONALLY_IDEMPOTENT_WITHOUT_A_SESSION` above):
    proves the actual, intended contract -- a sessionless logout returns 204 and sets no cookie
    -- rather than asserting nothing about this operation at all. Needs the SAME dummy Eskiz/etc.
    env vars `tests/e2e/conftest.py` already validates (reused here, function-scoped via
    `monkeypatch` so nothing leaks past this one test) -- without them, `get_authentication_use_
    cases`'s real dependency chain can't even construct, and the request 500s before reaching
    logout's own body at all (exactly the accidental-pass this test replaces, see the module
    docstring above)."""
    for key, value in _DEFAULT_ENV.items():
        monkeypatch.setenv(key, value)
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert "ah_session" not in response.cookies
