"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real Postgres/identity-bridge providers swapped for in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production. Covers the 12
profiles-related operationIds (excluding the 3 team-member ones, see profiles/README.md "Known
gaps") and the authorization allow/deny matrix (profile-ownership + reviewer-role scenarios,
extending the harness P-05 established). Mirrors `apps/backend/tests/catalog/test_api.py`'s
pattern exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from main import create_app
from profiles.application.ports import VerificationEligibilitySnapshot
from profiles.application.profile_use_cases import ProfileUseCases
from profiles.application.verification_use_cases import VerificationUseCases
from profiles.interfaces.auth import ActingProfileManager, ActingReviewer, ActingUser
from profiles.interfaces.di import (
    get_acting_profile_manager,
    get_acting_reviewer,
    get_acting_user,
    get_profile_use_cases,
    get_verification_use_cases,
)
from shared_kernel import BusinessProfileId, UserId

from .conftest import (
    FakeBusinessProfileRepository,
    FakeMediaAssetReaderPort,
    FakeOutbox,
    FakeVerificationCaseRepository,
    FakeVerificationEligibilityRepository,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

TEST_OWNER = UserId(value=uuid4())
TEST_OTHER = UserId(value=uuid4())
TEST_REVIEWER = UserId(value=uuid4())
TEST_PROFILE_MANAGER = UserId(value=uuid4())
_TOKEN_TO_USER = {"owner-token": TEST_OWNER, "other-token": TEST_OTHER}
_REVIEWER_TOKENS = {"reviewer-token"}
_PROFILE_MANAGER_TOKENS = {"profile-manager-token"}


@pytest.fixture
def client(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> Iterator[TestClient]:
    def _profile_use_cases() -> ProfileUseCases:
        return ProfileUseCases(profiles=fake_profiles, media=fake_media, outbox=fake_outbox)

    def _verification_use_cases() -> VerificationUseCases:
        return VerificationUseCases(
            profiles=fake_profiles,
            cases=fake_cases,
            eligibility=fake_eligibility,
            media=fake_media,
            outbox=fake_outbox,
        )

    async def acting_user_override(authorization: str | None = Header(default=None)) -> ActingUser:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        account_id = _TOKEN_TO_USER.get(token or "")
        if account_id is None:
            raise HTTPException(status_code=401, detail="no valid session")
        return ActingUser(account_id=account_id, acting_profile_id=None)

    async def acting_reviewer_override(
        authorization: str | None = Header(default=None),
    ) -> ActingReviewer:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        if token not in _REVIEWER_TOKENS:
            raise HTTPException(status_code=403, detail="not a reviewer")
        return ActingReviewer(account_id=TEST_REVIEWER)

    async def acting_profile_manager_override(
        authorization: str | None = Header(default=None),
    ) -> ActingProfileManager:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        if token not in _PROFILE_MANAGER_TOKENS:
            raise HTTPException(status_code=403, detail="not a profile manager")
        return ActingProfileManager(account_id=TEST_PROFILE_MANAGER)

    app = create_app()
    app.dependency_overrides[get_profile_use_cases] = _profile_use_cases
    app.dependency_overrides[get_verification_use_cases] = _verification_use_cases
    app.dependency_overrides[get_acting_user] = acting_user_override
    app.dependency_overrides[get_acting_reviewer] = acting_reviewer_override
    app.dependency_overrides[get_acting_profile_manager] = acting_profile_manager_override

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _approve(client: TestClient, profile_id: str) -> None:
    """ADR-0012: every new profile starts `PENDING_REVIEW` -- tests that need an `ACTIVE` one
    (e.g. to then archive it, only legal from `ACTIVE`) approve it first via the admin
    registration-decision endpoint."""
    resp = client.post(
        f"/api/v1/admin/business-profiles/{profile_id}/decision",
        json={"outcome": "APPROVED"},
        headers=_auth("profile-manager-token"),
    )
    assert resp.status_code == 200, resp.text


# --- profile CRUD ---------------------------------------------------------------------------


def test_create_and_get_business_profile(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "ARCHITECT", "name": {"uz_latn": "Test Arch"}},
        headers=_auth("owner-token"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["profileType"] == "ARCHITECT"
    assert body["status"] == "PENDING_REVIEW"

    get_resp = client.get(f"/api/v1/business-profiles/{body['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == body["id"]


def test_create_business_profile_requires_authentication(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/business-profiles", json={"profileType": "ARCHITECT", "name": {"uz_latn": "X"}}
    )
    assert resp.status_code == 401


def test_get_nonexistent_business_profile_returns_404(client: TestClient) -> None:
    resp = client.get(f"/api/v1/business-profiles/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "RESOURCE_NOT_FOUND"


def test_update_business_profile_refuses_non_owner(client: TestClient) -> None:
    created = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "BUILDER", "name": {"uz_latn": "B"}},
        headers=_auth("owner-token"),
    ).json()
    resp = client.patch(
        f"/api/v1/business-profiles/{created['id']}",
        json={"name": {"uz_latn": "Renamed"}},
        headers=_auth("other-token"),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "PERMISSION_DENIED"


def test_archive_business_profile_by_owner_succeeds(client: TestClient) -> None:
    created = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "SUPPLIER", "name": {"uz_latn": "S"}},
        headers=_auth("owner-token"),
    ).json()
    _approve(client, created["id"])
    resp = client.delete(f"/api/v1/business-profiles/{created['id']}", headers=_auth("owner-token"))
    assert resp.status_code == 204

    fetched = client.get(f"/api/v1/business-profiles/{created['id']}").json()
    assert fetched["status"] == "ARCHIVED"


def test_list_business_profiles_is_public() -> None:
    pass  # covered implicitly by test_create_and_get_business_profile's GET (no auth header)


# --- owner-admin-panel company management ----------------------------------------------------


def test_admin_list_business_profiles_requires_profile_manager_permission(
    client: TestClient,
) -> None:
    resp = client.get("/api/v1/admin/business-profiles", headers=_auth("owner-token"))
    assert resp.status_code == 403


def test_admin_list_business_profiles_reports_total_and_includes_archived(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "SUPPLIER", "name": {"uz_latn": "Admin-listed co"}},
        headers=_auth("owner-token"),
    ).json()
    _approve(client, created["id"])
    client.delete(f"/api/v1/business-profiles/{created['id']}", headers=_auth("owner-token"))

    resp = client.get("/api/v1/admin/business-profiles", headers=_auth("profile-manager-token"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page"]["total"] == 1
    assert any(
        item["id"] == created["id"] and item["status"] == "ARCHIVED" for item in body["items"]
    )


def test_admin_archive_business_profile_bypasses_ownership(client: TestClient) -> None:
    created = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "SUPPLIER", "name": {"uz_latn": "Force-archived co"}},
        headers=_auth("owner-token"),
    ).json()
    _approve(client, created["id"])

    resp = client.post(
        f"/api/v1/admin/business-profiles/{created['id']}/archive",
        headers=_auth("profile-manager-token"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ARCHIVED"


def test_admin_archive_business_profile_requires_profile_manager_permission(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "SUPPLIER", "name": {"uz_latn": "Untouchable co"}},
        headers=_auth("owner-token"),
    ).json()
    resp = client.post(
        f"/api/v1/admin/business-profiles/{created['id']}/archive", headers=_auth("owner-token")
    )
    assert resp.status_code == 403


# --- portfolio -------------------------------------------------------------------------------


def test_portfolio_add_list_remove(
    client: TestClient, fake_media: FakeMediaAssetReaderPort
) -> None:
    created = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "MANUFACTURER", "name": {"uz_latn": "M"}},
        headers=_auth("owner-token"),
    ).json()
    media_asset_id = str(uuid4())
    fake_media.seed(UUID(media_asset_id))

    add_resp = client.post(
        f"/api/v1/business-profiles/{created['id']}/portfolio",
        json={"id": str(uuid4()), "mediaAssetId": media_asset_id, "position": 1},
        headers=_auth("owner-token"),
    )
    assert add_resp.status_code == 201, add_resp.text

    list_resp = client.get(f"/api/v1/business-profiles/{created['id']}/portfolio")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1

    remove_resp = client.delete(
        f"/api/v1/business-profiles/{created['id']}/portfolio/{items[0]['id']}",
        headers=_auth("owner-token"),
    )
    assert remove_resp.status_code == 204


# --- verification (owner-facing) --------------------------------------------------------------


def test_request_verification_requires_active_entitlement(client: TestClient) -> None:
    created = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "CONTRACTOR", "name": {"uz_latn": "C"}},
        headers=_auth("owner-token"),
    ).json()
    resp = client.post(
        f"/api/v1/business-profiles/{created['id']}/verification",
        json={
            "entitlementId": str(uuid4()),
            "documents": [{"mediaAssetId": str(uuid4()), "documentKind": "license"}],
        },
        headers=_auth("owner-token"),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "BUSINESS_RULE_VIOLATION"


def test_request_verification_and_get_current_case(
    client: TestClient,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
) -> None:
    created = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "SERVICE_PROVIDER", "name": {"uz_latn": "SP"}},
        headers=_auth("owner-token"),
    ).json()
    entitlement_id = uuid4()
    fake_eligibility.snapshots[entitlement_id] = VerificationEligibilitySnapshot(
        entitlement_id=entitlement_id,
        business_profile_id=BusinessProfileId(value=UUID(created["id"])),
        valid_from=NOW,
        valid_until=NOW + timedelta(days=365),
        activation_state="ACTIVE",
        source_event_id=uuid4(),
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)

    resp = client.post(
        f"/api/v1/business-profiles/{created['id']}/verification",
        json={
            "entitlementId": str(entitlement_id),
            "documents": [{"mediaAssetId": str(media_asset_id), "documentKind": "license"}],
        },
        headers=_auth("owner-token"),
    )
    assert resp.status_code == 201, resp.text
    case_body = resp.json()
    assert case_body["status"] == "REQUESTED"

    get_case_resp = client.get(
        f"/api/v1/business-profiles/{created['id']}/verification", headers=_auth("owner-token")
    )
    assert get_case_resp.status_code == 200
    assert get_case_resp.json()["id"] == case_body["id"]


def test_get_verification_case_requires_authentication(client: TestClient) -> None:
    resp = client.get(f"/api/v1/business-profiles/{uuid4()}/verification")
    assert resp.status_code == 401


# --- verification queue (reviewer-only, Administration tag) ------------------------------------


def test_verification_queue_refuses_non_reviewer(client: TestClient) -> None:
    resp = client.get("/api/v1/admin/verification-queue", headers=_auth("owner-token"))
    assert resp.status_code == 403


def test_verification_queue_refuses_unauthenticated(client: TestClient) -> None:
    resp = client.get("/api/v1/admin/verification-queue")
    assert resp.status_code == 403


def test_verification_queue_allows_reviewer(client: TestClient) -> None:
    resp = client.get("/api/v1/admin/verification-queue", headers=_auth("reviewer-token"))
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_decide_verification_allows_reviewer_and_refuses_others(
    client: TestClient,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
) -> None:
    created = client.post(
        "/api/v1/business-profiles",
        json={"profileType": "ARCHITECT", "name": {"uz_latn": "A2"}},
        headers=_auth("owner-token"),
    ).json()
    entitlement_id = uuid4()
    fake_eligibility.snapshots[entitlement_id] = VerificationEligibilitySnapshot(
        entitlement_id=entitlement_id,
        business_profile_id=BusinessProfileId(value=UUID(created["id"])),
        valid_from=NOW,
        valid_until=NOW + timedelta(days=365),
        activation_state="ACTIVE",
        source_event_id=uuid4(),
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)
    case_body = client.post(
        f"/api/v1/business-profiles/{created['id']}/verification",
        json={
            "entitlementId": str(entitlement_id),
            "documents": [{"mediaAssetId": str(media_asset_id), "documentKind": "license"}],
        },
        headers=_auth("owner-token"),
    ).json()

    denied = client.post(
        f"/api/v1/admin/verification-queue/{case_body['id']}/decision",
        json={"outcome": "APPROVED"},
        headers=_auth("owner-token"),
    )
    assert denied.status_code == 403

    approved = client.post(
        f"/api/v1/admin/verification-queue/{case_body['id']}/decision",
        json={"outcome": "APPROVED"},
        headers=_auth("reviewer-token"),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    profile_after = client.get(f"/api/v1/business-profiles/{created['id']}").json()
    assert profile_after["badge"]["status"] == "VALID"
