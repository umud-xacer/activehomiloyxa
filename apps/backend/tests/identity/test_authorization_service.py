"""Unit tests for `ApplicationAuthorizationService` -- Security Sec 4.2 Gates 1-2 (session
validity, acting-context resolution) against in-memory fakes, delegating Gates 3-4 to the
already-tested domain `AuthorizationService` (see `test_authorization.py`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from identity.application.authorization_service import ApplicationAuthorizationService
from identity.application.exceptions import AccountNotFoundError, InvalidSessionTokenError
from identity.domain import (
    AccountNotActiveError,
    PermissionDeniedError,
    PhoneNumber,
    Session,
    SessionExpiredError,
    UserAccount,
)
from shared_kernel import BusinessProfileId, UserId

from .conftest import FakeRoleDefinitionReader, FakeSessionRepository, FakeUserAccountRepository

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _seeded_account() -> UserAccount:
    return UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()), phone=PhoneNumber("+998901234567"), now=NOW
    )


@pytest.fixture
def authz_service(
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_role_reader: FakeRoleDefinitionReader,
) -> ApplicationAuthorizationService:
    return ApplicationAuthorizationService(
        session_repo=fake_sessions, account_repo=fake_accounts, role_reader=fake_role_reader
    )


async def _seed_session(
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    account: UserAccount,
    *,
    expires_at: datetime = NOW + timedelta(hours=720),
) -> Session:
    await fake_accounts.add(account)
    session = Session.issue(
        session_id=uuid4(),
        account_id=account.id,
        token_hash="tok-hash",
        ip_address=None,
        user_agent=None,
        now=NOW,
        expires_at=expires_at,
    )
    await fake_sessions.save(session)
    return session


async def test_resolve_acting_context_returns_account_session_and_permissions(
    authz_service: ApplicationAuthorizationService,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_role_reader: FakeRoleDefinitionReader,
) -> None:
    account = _seeded_account()
    resolved = fake_role_reader.register_role("administrator", frozenset({"identity:role:assign"}))
    account = account.assign_role(
        role_definition_head_id=resolved.head_id,
        role_definition_version_id=resolved.version_id,
        role_code="administrator",
        acting_profile_id=None,
        assigned_by=uuid4(),
        now=NOW,
    )
    session = await _seed_session(fake_accounts, fake_sessions, account)

    resolved_account, resolved_session, context = await authz_service.resolve_acting_context(
        token_hash="tok-hash", now=NOW
    )
    assert resolved_account.id == account.id
    assert resolved_session.id == session.id
    assert context.effective_permissions == frozenset({"identity:role:assign"})


async def test_resolve_acting_context_invalid_token_raises(
    authz_service: ApplicationAuthorizationService,
) -> None:
    with pytest.raises(InvalidSessionTokenError):
        await authz_service.resolve_acting_context(token_hash="no-such-token", now=NOW)


async def test_resolve_acting_context_expired_session_raises(
    authz_service: ApplicationAuthorizationService,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
) -> None:
    account = _seeded_account()
    await _seed_session(fake_accounts, fake_sessions, account, expires_at=NOW - timedelta(hours=1))
    with pytest.raises(SessionExpiredError):
        await authz_service.resolve_acting_context(token_hash="tok-hash", now=NOW)


async def test_resolve_acting_context_missing_account_raises(
    authz_service: ApplicationAuthorizationService, fake_sessions: FakeSessionRepository
) -> None:
    session = Session.issue(
        session_id=uuid4(),
        account_id=UserId(value=uuid4()),
        token_hash="tok-hash",
        ip_address=None,
        user_agent=None,
        now=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    await fake_sessions.save(session)
    with pytest.raises(AccountNotFoundError):
        await authz_service.resolve_acting_context(token_hash="tok-hash", now=NOW)


async def test_resolve_acting_context_suspended_account_raises(
    authz_service: ApplicationAuthorizationService,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
) -> None:
    account = _seeded_account().suspend(now=NOW)
    await _seed_session(fake_accounts, fake_sessions, account)
    with pytest.raises(AccountNotActiveError):
        await authz_service.resolve_acting_context(token_hash="tok-hash", now=NOW)


async def test_authorize_success_returns_context(
    authz_service: ApplicationAuthorizationService,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_role_reader: FakeRoleDefinitionReader,
) -> None:
    account = _seeded_account()
    resolved = fake_role_reader.register_role("administrator", frozenset({"identity:role:assign"}))
    account = account.assign_role(
        role_definition_head_id=resolved.head_id,
        role_definition_version_id=resolved.version_id,
        role_code="administrator",
        acting_profile_id=None,
        assigned_by=uuid4(),
        now=NOW,
    )
    await _seed_session(fake_accounts, fake_sessions, account)

    context = await authz_service.authorize(
        token_hash="tok-hash", required_permission="identity:role:assign", now=NOW
    )
    assert context.account_id == account.id


async def test_authorize_no_permission_denies(
    authz_service: ApplicationAuthorizationService,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
) -> None:
    account = _seeded_account()
    await _seed_session(fake_accounts, fake_sessions, account)
    with pytest.raises(PermissionDeniedError):
        await authz_service.authorize(
            token_hash="tok-hash", required_permission="identity:role:assign", now=NOW
        )


async def test_effective_permissions_unions_multiple_role_assignments(
    authz_service: ApplicationAuthorizationService, fake_role_reader: FakeRoleDefinitionReader
) -> None:
    account = _seeded_account()
    first = fake_role_reader.register_role("role-a", frozenset({"perm:a"}))
    second = fake_role_reader.register_role("role-b", frozenset({"perm:b"}))
    account = account.assign_role(
        role_definition_head_id=first.head_id,
        role_definition_version_id=first.version_id,
        role_code="role-a",
        acting_profile_id=None,
        assigned_by=uuid4(),
        now=NOW,
    ).assign_role(
        role_definition_head_id=second.head_id,
        role_definition_version_id=second.version_id,
        role_code="role-b",
        acting_profile_id=None,
        assigned_by=uuid4(),
        now=NOW,
    )
    permissions = await authz_service.effective_permissions(account, None)
    assert permissions == frozenset({"perm:a", "perm:b"})


async def test_effective_permissions_excludes_other_profile_scoped_roles(
    authz_service: ApplicationAuthorizationService, fake_role_reader: FakeRoleDefinitionReader
) -> None:
    account = _seeded_account()
    profile_a = BusinessProfileId(value=uuid4())
    profile_b = BusinessProfileId(value=uuid4())
    resolved = fake_role_reader.register_role("profile-a-role", frozenset({"perm:a"}))
    account = account.assign_role(
        role_definition_head_id=resolved.head_id,
        role_definition_version_id=resolved.version_id,
        role_code="profile-a-role",
        acting_profile_id=profile_a,
        assigned_by=uuid4(),
        now=NOW,
    )
    permissions = await authz_service.effective_permissions(account, profile_b)
    assert permissions == frozenset()
