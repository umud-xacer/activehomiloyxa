"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition
root's real Postgres/Redis providers swapped for the in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production, no real datastore
needed. Covers every Authentication/Users operationId, contract-conformance (status codes, the
`ah_session` cookie), and the negative-path 401/403 cases the P-05 validation checklist requires.
A handful of true end-to-end integration tests against real Postgres/Redis live under
`integration/`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import Cookie, Header
from fastapi.testclient import TestClient

from identity.application import AccountUseCases, AuthenticationUseCases
from identity.application.authorization_service import ApplicationAuthorizationService
from identity.application.exceptions import InvalidSessionTokenError
from identity.interfaces.auth import SESSION_COOKIE_NAME, AuthenticatedRequest
from identity.interfaces.di import (
    get_account_use_cases,
    get_authenticated_request,
    get_authentication_use_cases,
)
from main import create_app

from .conftest import (
    FakeEmailProvider,
    FakeGoogleOAuthProvider,
    FakeLoginAttemptTracker,
    FakeOtpChallengeRepository,
    FakeOtpChallengeUnitOfWork,
    FakeOtpCodeGenerator,
    FakeOtpSmsProvider,
    FakeOutbox,
    FakePlatformSettingsReader,
    FakeRoleDefinitionReader,
    FakeSessionRepository,
    FakeSessionTokenGenerator,
    FakeUserAccountRepository,
)


@pytest.fixture
def client(
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_otp_challenges: FakeOtpChallengeRepository,
    fake_outbox: FakeOutbox,
    fake_role_reader: FakeRoleDefinitionReader,
    fake_platform_settings: FakePlatformSettingsReader,
    fake_login_attempts: FakeLoginAttemptTracker,
) -> Iterator[TestClient]:
    from identity.infrastructure.security import Argon2PasswordHasherAdapter

    token_generator = FakeSessionTokenGenerator()
    password_hasher = Argon2PasswordHasherAdapter()
    otp_challenge_unit_of_work = FakeOtpChallengeUnitOfWork(fake_otp_challenges)

    def _authentication_use_cases() -> AuthenticationUseCases:
        return AuthenticationUseCases(
            accounts=fake_accounts,
            sessions=fake_sessions,
            otp_challenges=fake_otp_challenges,
            otp_challenge_unit_of_work=otp_challenge_unit_of_work,
            outbox=fake_outbox,
            otp_sms_provider=FakeOtpSmsProvider(),
            email_provider=FakeEmailProvider(),
            google_provider=FakeGoogleOAuthProvider(),
            password_hasher=password_hasher,
            otp_code_generator=FakeOtpCodeGenerator(),
            session_token_generator=token_generator,
            platform_settings=fake_platform_settings,
            login_attempts=fake_login_attempts,
        )

    def _account_use_cases() -> AccountUseCases:
        return AccountUseCases(
            accounts=fake_accounts,
            sessions=fake_sessions,
            outbox=fake_outbox,
            password_hasher=password_hasher,
        )

    async def _authenticated_request(
        ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        authorization: str | None = Header(default=None),
    ) -> AuthenticatedRequest:
        raw_token = ah_session
        if raw_token is None and authorization and authorization.lower().startswith("bearer "):
            raw_token = authorization[len("bearer ") :].strip()
        if not raw_token:
            raise InvalidSessionTokenError()
        authz = ApplicationAuthorizationService(
            session_repo=fake_sessions, account_repo=fake_accounts, role_reader=fake_role_reader
        )
        token_hash = token_generator.hash_token(raw_token)
        account, session, _context = await authz.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return AuthenticatedRequest(account=account, session=session)

    app = create_app()
    app.dependency_overrides[get_authentication_use_cases] = _authentication_use_cases
    app.dependency_overrides[get_account_use_cases] = _account_use_cases
    app.dependency_overrides[get_authenticated_request] = _authenticated_request

    with TestClient(
        app, base_url="https://testserver", raise_server_exceptions=False
    ) as test_client:
        yield test_client


def test_health_ok(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


# --- Authentication ------------------------------------------------------------------------


def test_register_email_returns_202(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register/email",
        json={"email": "test@example.com", "password": "s3cret123", "displayName": "Test"},
    )
    assert response.status_code == 202


def test_register_email_duplicate_returns_409(client: TestClient) -> None:
    body = {"email": "test@example.com", "password": "s3cret123"}
    client.post("/api/v1/auth/register/email", json=body)
    response = client.post("/api/v1/auth/register/email", json=body)
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_KEY"


def test_login_email_sets_session_cookie_and_returns_account(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register/email", json={"email": "test@example.com", "password": "s3cret123"}
    )
    response = client.post(
        "/api/v1/auth/login/email", json={"email": "test@example.com", "password": "s3cret123"}
    )
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies
    body = response.json()
    assert body["account"]["email"] == "test@example.com"
    assert body["sessionToken"]


def test_login_email_wrong_password_returns_401(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register/email", json={"email": "test@example.com", "password": "s3cret123"}
    )
    response = client.post(
        "/api/v1/auth/login/email", json={"email": "test@example.com", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_INVALID"


def test_login_email_locked_out_after_repeated_failures_returns_429_with_retry_after(
    client: TestClient,
) -> None:
    """End-to-end through the real HTTP layer (routing, `_client_ip`, error middleware) rather
    than the use-case layer directly -- also verifies the `Retry-After` header the `TooManyRequests`
    contract component declares but, before this task, nothing in `backbone.errors` ever
    populated for ANY 429 (OTP throttle/messaging rate limit had the identical gap)."""
    client.post(
        "/api/v1/auth/register/email", json={"email": "test@example.com", "password": "s3cret123"}
    )
    for _ in range(4):
        response = client.post(
            "/api/v1/auth/login/email", json={"email": "test@example.com", "password": "wrong"}
        )
        assert response.status_code == 401

    # 5th attempt -- correct password, but the account is already locked out.
    response = client.post(
        "/api/v1/auth/login/email", json={"email": "test@example.com", "password": "s3cret123"}
    )
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert int(response.headers["retry-after"]) > 0


def test_request_otp_returns_202(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/otp", json={"phoneNumber": "+998901234567", "purpose": "REGISTRATION"}
    )
    assert response.status_code == 202


def test_verify_otp_wrong_code_returns_422(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/otp", json={"phoneNumber": "+998901234567", "purpose": "REGISTRATION"}
    )
    response = client.post(
        "/api/v1/auth/otp/verify",
        json={"phoneNumber": "+998901234567", "code": "000000", "purpose": "REGISTRATION"},
    )
    assert response.status_code == 422


def test_logout_clears_cookie(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register/email", json={"email": "test@example.com", "password": "s3cret123"}
    )
    client.post(
        "/api/v1/auth/login/email", json={"email": "test@example.com", "password": "s3cret123"}
    )
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204


def test_start_recovery_returns_202(client: TestClient) -> None:
    response = client.post("/api/v1/auth/recovery", json={"email": "nobody@example.com"})
    assert response.status_code == 202


# --- negative path: 401 for unauthenticated Users operations -------------------------------


def test_get_me_without_session_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_update_me_without_session_returns_401(client: TestClient) -> None:
    response = client.patch("/api/v1/me", json={"displayName": "X"})
    assert response.status_code == 401


def test_list_sessions_without_session_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/me/sessions")
    assert response.status_code == 401


# --- Users (session-authenticated) ----------------------------------------------------------


def _register_and_login(client: TestClient, email: str = "test@example.com") -> None:
    client.post("/api/v1/auth/register/email", json={"email": email, "password": "s3cret123"})
    client.post("/api/v1/auth/login/email", json={"email": email, "password": "s3cret123"})


def test_get_me_with_session_returns_account(client: TestClient) -> None:
    _register_and_login(client)
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


def test_update_me_changes_display_name(client: TestClient) -> None:
    _register_and_login(client)
    response = client.patch("/api/v1/me", json={"displayName": "New Name"})
    assert response.status_code == 200
    assert response.json()["displayName"] == "New Name"


def test_change_password_wrong_current_returns_401(client: TestClient) -> None:
    _register_and_login(client)
    response = client.put(
        "/api/v1/me/password",
        json={"currentPassword": "wrong", "newPassword": "newpassword123"},
    )
    assert response.status_code == 401


def test_change_password_success_returns_204(client: TestClient) -> None:
    _register_and_login(client)
    response = client.put(
        "/api/v1/me/password",
        json={"currentPassword": "s3cret123", "newPassword": "newpassword123"},
    )
    assert response.status_code == 204


def test_update_preferences_changes_phone_reveal_mode(client: TestClient) -> None:
    _register_and_login(client)
    response = client.put(
        "/api/v1/me/preferences", json={"privacySettings": {"phoneRevealMode": "NEVER"}}
    )
    assert response.status_code == 200
    assert response.json()["privacySettings"]["phoneRevealMode"] == "NEVER"


def test_close_account_returns_204(client: TestClient) -> None:
    _register_and_login(client)
    response = client.delete("/api/v1/me/account")
    assert response.status_code == 204


def test_list_sessions_includes_current_session(client: TestClient) -> None:
    _register_and_login(client)
    response = client.get("/api/v1/me/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["current"] is True


def test_revoke_session_of_another_account_returns_404(client: TestClient) -> None:
    _register_and_login(client, email="me@example.com")
    my_response = client.get("/api/v1/me/sessions")
    my_session_id = my_response.json()[0]["id"]

    # Different client (separate cookie jar) for a second account.
    other = TestClient(client.app, base_url="https://testserver", raise_server_exceptions=False)
    _register_and_login(other, email="other@example.com")

    response = other.delete(f"/api/v1/me/sessions/{my_session_id}")
    assert response.status_code == 404


def test_switch_acting_profile_to_unowned_profile_returns_403(client: TestClient) -> None:
    _register_and_login(client)
    response = client.post(
        "/api/v1/me/sessions/switch-profile",
        json={"actingProfileId": "11111111-1111-1111-1111-111111111111"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "WRONG_ACTING_PROFILE"
