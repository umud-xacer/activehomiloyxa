"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition
root's real Postgres/Redis providers swapped for the in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production, no real datastore
needed. A handful of true end-to-end integration tests against real Postgres/Redis live under
`integration/`.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from apps.backend.tests.configuration.conftest import (
    FakeConfigHeadRepository,
    FakeOutbox,
    FakeOwnerAdminLockoutCounter,
    FakeSnapshotCache,
)
from fastapi import Header
from fastapi.testclient import TestClient

from configuration.application.category_read import CategoryReadUseCases
from configuration.application.use_cases import ConfigurationUseCases
from configuration.interfaces.auth import ActingAdmin, get_acting_admin
from configuration.interfaces.di import (
    get_category_read_use_cases,
    get_configuration_use_cases,
    get_owner_admin_lockout_counter,
)
from main import create_app

MAKER = "11111111-1111-1111-1111-111111111111"
CHECKER = "22222222-2222-2222-2222-222222222222"


def _headers(actor: str, keys: list[str]) -> dict[str, str]:
    return {"X-Actor-Id": actor, "X-Permission-Keys": ",".join(keys)}


async def _acting_admin_from_headers(
    x_actor_id: UUID = Header(..., alias="X-Actor-Id"),
    x_permission_keys: str = Header("", alias="X-Permission-Keys"),
) -> ActingAdmin:
    """Test-harness-only acting-admin resolution from headers.

    Production resolves this from the `ah_session` cookie via identity's real
    `AuthorizationService` -- header-trusting resolution was DEF-01, a genuine vulnerability, and
    is gone from `create_app`. These tests still express *which* actor holds *which* keys through
    headers because that is the clearest way to write a maker-checker scenario (MAKER and CHECKER
    are two distinct principals), so the test app opts back into it explicitly.

    That opt-in is the important word: the capability now exists only where a test asks for it by
    name, instead of being what every real deployment did by default. `tests/authorization/
    test_configuration_admin_default_deny.py` asserts the production app refuses these same
    headers.
    """
    keys = frozenset(key.strip() for key in x_permission_keys.split(",") if key.strip())
    return ActingAdmin(actor_id=x_actor_id, permission_keys=keys)


@pytest.fixture
def client(
    fake_repo: FakeConfigHeadRepository,
    fake_cache: FakeSnapshotCache,
    fake_outbox: FakeOutbox,
    fake_owner_admin_lockout: FakeOwnerAdminLockoutCounter,
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_configuration_use_cases] = lambda: ConfigurationUseCases(
        fake_repo, fake_cache, fake_outbox
    )
    app.dependency_overrides[get_category_read_use_cases] = lambda: CategoryReadUseCases(
        fake_repo, fake_cache
    )
    app.dependency_overrides[get_acting_admin] = _acting_admin_from_headers
    app.dependency_overrides[get_owner_admin_lockout_counter] = lambda: fake_owner_admin_lockout
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_create_draft_requires_manage_permission(client: TestClient) -> None:
    response = client.post(
        "/api/v1/admin/config/search-configuration",
        json={
            "code": "search-default",
            "businessOwner": "Product Owner",
            "definition": {
                "descriptor": {"name": {"uz_latn": "Default search"}},
                "sort_options": ["RELEVANCE", "RECENCY"],
                "default_sort": "RELEVANCE",
                "promotion_page_cap": 5,
            },
        },
        headers=_headers(MAKER, []),  # no permission keys at all
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_standard_track_full_lifecycle(client: TestClient) -> None:
    create = client.post(
        "/api/v1/admin/config/search-configuration",
        json={
            "code": "search-default",
            "businessOwner": "Product Owner",
            "definition": {
                "descriptor": {"name": {"uz_latn": "Default search"}},
                "sort_options": ["RELEVANCE", "RECENCY"],
                "default_sort": "RELEVANCE",
                "promotion_page_cap": 5,
            },
        },
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    assert create.status_code == 201, create.text
    version = create.json()
    assert version["status"] == "DRAFT"
    head_id, version_id = version["headId"], version["id"]

    validate = client.post(
        f"/api/v1/admin/config/search-configuration/{head_id}/versions/{version_id}/validate",
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    assert validate.status_code == 200
    assert validate.json()["valid"] is True

    publish = client.post(
        f"/api/v1/admin/config/search-configuration/{head_id}/versions/{version_id}/publish",
        json={"approvalNote": None},
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    assert publish.status_code == 200
    assert publish.json()["status"] == "PUBLISHED"

    head = client.get(
        f"/api/v1/admin/config/search-configuration/{head_id}",
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    assert head.status_code == 200
    assert head.json()["status"] == "PUBLISHED"

    listed = client.get(
        "/api/v1/admin/config/search-configuration",
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    assert listed.status_code == 200
    assert any(item["id"] == head_id for item in listed.json()["items"])


def test_gate_failure_returns_422_with_validation_errors(client: TestClient) -> None:
    create = client.post(
        "/api/v1/admin/config/search-configuration",
        json={
            "code": "search-broken",
            "businessOwner": "Product Owner",
            "definition": {
                "descriptor": {"name": {"uz_latn": "Broken search"}},
                "sort_options": ["RECENCY"],
                "default_sort": "RELEVANCE",  # not in sort_options -> CONFLICTING_RULE
                "promotion_page_cap": 5,
            },
        },
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    version = create.json()
    publish = client.post(
        f"/api/v1/admin/config/search-configuration/{version['headId']}/versions/{version['id']}/publish",
        json={"approvalNote": None},
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    assert publish.status_code == 422
    body = publish.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["errors"][0]["rule"] == "CONFLICTING_RULE"


def test_get_unknown_head_is_404(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/admin/config/search-configuration/{uuid4()}",
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_controlled_track_two_call_publish_via_api(client: TestClient) -> None:
    create = client.post(
        "/api/v1/admin/config/role-definition",
        json={
            "code": "content-editor",
            "businessOwner": "Super Administrator",
            "definition": {
                "descriptor": {"name": {"uz_latn": "Content Editor"}},
                "role_name": "Content Editor",
                "permission_keys": ["config:notification-template:manage"],
            },
        },
        headers=_headers(MAKER, ["config:role-definition:manage"]),
    )
    version = create.json()
    head_id, version_id = version["headId"], version["id"]

    maker_call = client.post(
        f"/api/v1/admin/config/role-definition/{head_id}/versions/{version_id}/publish",
        json={"approvalNote": "please review"},
        headers=_headers(MAKER, ["config:role-definition:manage"]),
    )
    assert maker_call.status_code == 200
    assert maker_call.json()["status"] == "APPROVAL"

    self_approve = client.post(
        f"/api/v1/admin/config/role-definition/{head_id}/versions/{version_id}/publish",
        json={"approvalNote": "self"},
        headers=_headers(
            MAKER, ["config:role-definition:manage", "config:role-definition:approve"]
        ),
    )
    assert self_approve.status_code == 403
    assert self_approve.json()["code"] == "PERMISSION_DENIED"

    checker_no_approve = client.post(
        f"/api/v1/admin/config/role-definition/{head_id}/versions/{version_id}/publish",
        json={"approvalNote": "no approve key"},
        headers=_headers(CHECKER, ["config:role-definition:manage"]),
    )
    assert checker_no_approve.status_code == 403
    assert checker_no_approve.json()["code"] == "PERMISSION_DENIED"

    checker_call = client.post(
        f"/api/v1/admin/config/role-definition/{head_id}/versions/{version_id}/publish",
        json={"approvalNote": "approved"},
        headers=_headers(
            CHECKER, ["config:role-definition:manage", "config:role-definition:approve"]
        ),
    )
    assert checker_call.status_code == 200
    assert checker_call.json()["status"] == "PUBLISHED"


def test_UNF_029_publish_accepts_no_request_body(client: TestClient) -> None:
    """`publishConfigVersion`'s requestBody carries no `required: true` in the frozen contract,
    but the router used to declare a mandatory Pydantic body param, so a client that (correctly,
    per the contract) sent no body at all got 422 instead of a publish. `approvalNote` is
    optional on `ConfigPublishRequest` itself, so "no body" and "an empty body" both mean "no
    approval note" -- this is a self-service-track entity (search-configuration), so one call
    publishes it outright."""
    create = client.post(
        "/api/v1/admin/config/search-configuration",
        json={
            "code": "no-body-publish",
            "businessOwner": "Product Owner",
            "definition": {
                "descriptor": {"name": {"uz_latn": "No-body publish"}},
                "sort_options": ["RELEVANCE"],
                "default_sort": "RELEVANCE",
                "promotion_page_cap": 0,
            },
        },
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    head_id, version_id = create.json()["headId"], create.json()["id"]

    response = client.post(
        f"/api/v1/admin/config/search-configuration/{head_id}/versions/{version_id}/publish",
        headers=_headers(MAKER, ["config:search-configuration:manage"]),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PUBLISHED"


def test_public_categories_endpoints_need_no_auth(client: TestClient) -> None:
    form_create = client.post(
        "/api/v1/admin/config/form-definition",
        json={
            "code": "housing-form",
            "businessOwner": "Product Owner",
            "definition": {
                "descriptor": {"name": {"uz_latn": "Housing form"}},
                "sections": [{"code": "main", "label": {"uz_latn": "Main"}, "order": 1}],
                "fields": [],
            },
        },
        headers=_headers(MAKER, ["config:form-definition:manage"]),
    )
    form_version = form_create.json()
    client.post(
        f"/api/v1/admin/config/form-definition/{form_version['headId']}/versions/{form_version['id']}/publish",
        json={"approvalNote": "submit"},
        headers=_headers(MAKER, ["config:form-definition:manage"]),
    )
    form_publish = client.post(
        f"/api/v1/admin/config/form-definition/{form_version['headId']}/versions/{form_version['id']}/publish",
        json={"approvalNote": "approve"},
        headers=_headers(
            CHECKER, ["config:form-definition:manage", "config:form-definition:approve"]
        ),
    )
    assert form_publish.status_code == 200

    cat_create = client.post(
        "/api/v1/admin/config/category",
        json={
            "code": "housing",
            "businessOwner": "Product Owner",
            "definition": {
                "descriptor": {"name": {"uz_latn": "Housing"}},
                "parent_category_id": None,
                "path": "/housing",
                "form_definition_id": form_version["headId"],
                "tree_status": "ACTIVE",
            },
        },
        headers=_headers(MAKER, ["config:category:manage"]),
    )
    cat_version = cat_create.json()
    client.post(
        f"/api/v1/admin/config/category/{cat_version['headId']}/versions/{cat_version['id']}/publish",
        json={"approvalNote": "submit"},
        headers=_headers(MAKER, ["config:category:manage"]),
    )
    cat_publish = client.post(
        f"/api/v1/admin/config/category/{cat_version['headId']}/versions/{cat_version['id']}/publish",
        json={"approvalNote": "approve"},
        headers=_headers(CHECKER, ["config:category:manage", "config:category:approve"]),
    )
    assert cat_publish.status_code == 200

    # -- no auth headers at all from here on --------------------------------------------------
    listed = client.get("/api/v1/categories")
    assert listed.status_code == 200
    assert any(c["id"] == cat_version["headId"] for c in listed.json())

    got = client.get(f"/api/v1/categories/{cat_version['headId']}")
    assert got.status_code == 200

    form = client.get(f"/api/v1/categories/{cat_version['headId']}/form")
    assert form.status_code == 200
    assert form.json()["id"] == form_version["headId"]

    missing = client.get(f"/api/v1/categories/{uuid4()}")
    assert missing.status_code == 404


# --- verifyOwnerAdminSlug + its IP-scoped lockout -------------------------------------------


def test_verify_owner_admin_slug_correct_guess_is_valid(client: TestClient) -> None:
    """No `platform-settings-global` head exists in `fake_repo` by default, so the real slug is
    the built-in default (`interfaces/routers.py`'s `_OWNER_ADMIN_SLUG_DEFAULT`)."""
    response = client.post("/api/v1/public/owner-admin-access/verify", json={"slug": "owner-admin"})
    assert response.status_code == 200
    assert response.json() == {"valid": True}


def test_verify_owner_admin_slug_wrong_guess_is_invalid(client: TestClient) -> None:
    response = client.post("/api/v1/public/owner-admin-access/verify", json={"slug": "not-it"})
    assert response.status_code == 200
    assert response.json() == {"valid": False}


def test_verify_owner_admin_slug_locks_out_after_repeated_wrong_guesses(
    client: TestClient,
) -> None:
    for _ in range(5):
        response = client.post("/api/v1/public/owner-admin-access/verify", json={"slug": "not-it"})
        assert response.status_code == 200

    locked = client.post("/api/v1/public/owner-admin-access/verify", json={"slug": "not-it"})
    assert locked.status_code == 429
    assert locked.json()["code"] == "RATE_LIMITED"
    assert "retry-after" in locked.headers

    # A correct guess is refused too while locked out -- the oracle answers nothing at all once
    # the caller has been rate-limited, not even a true "valid": True.
    still_locked = client.post(
        "/api/v1/public/owner-admin-access/verify", json={"slug": "owner-admin"}
    )
    assert still_locked.status_code == 429


def test_verify_owner_admin_slug_correct_guess_resets_the_lockout_counter(
    client: TestClient, fake_owner_admin_lockout: FakeOwnerAdminLockoutCounter
) -> None:
    client.post("/api/v1/public/owner-admin-access/verify", json={"slug": "not-it"})
    client.post("/api/v1/public/owner-admin-access/verify", json={"slug": "owner-admin"})
    assert fake_owner_admin_lockout.counts == {}


# --- getFeatureFlags ---------------------------------------------------------------------------


def test_get_feature_flags_defaults_skyscraper_ads_to_false(client: TestClient) -> None:
    """No `platform-settings-global` head exists in `fake_repo` by default, so the key is unset
    -- must default to `False` (site owner's explicit default-off requirement), never 500."""
    response = client.get("/api/v1/public/feature-flags")
    assert response.status_code == 200
    assert response.json() == {"skyscraperAdsEnabled": False}


# --- getCurrencyRate ----------------------------------------------------------------------------


def test_get_currency_rate_defaults_to_a_nonzero_rate(client: TestClient) -> None:
    """No `platform-settings-global` head exists in `fake_repo` by default, so the key is unset
    -- must default to a real nonzero rate (never 0, which would break client-side division),
    never 500."""
    response = client.get("/api/v1/public/currency-rate")
    assert response.status_code == 200
    body = response.json()
    assert body["usdUzsRate"] > 0
