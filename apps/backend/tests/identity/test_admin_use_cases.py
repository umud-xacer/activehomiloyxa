"""Unit tests for `AdminIdentityUseCases` (suspend/reactivate, list users, assign/revoke role)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from identity.application import (
    AccountNotFoundError,
    AdminIdentityUseCases,
    RoleDefinitionNotFoundError,
)
from identity.domain import (
    AccountStatus,
    EmailAddress,
    PhoneNumber,
    RoleNotAssignedError,
    Session,
    UserAccount,
)
from shared_kernel import UserId

from .conftest import (
    FakeOutbox,
    FakeRoleDefinitionReader,
    FakeSessionRepository,
    FakeUserAccountRepository,
)

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _seeded_account() -> UserAccount:
    return UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()), phone=PhoneNumber("+998901234567"), now=NOW
    )


async def test_change_user_status_suspend_revokes_sessions_and_publishes_event(
    admin_use_cases: AdminIdentityUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    account = _seeded_account()
    await fake_accounts.add(account)
    session = Session.issue(
        session_id=uuid4(),
        account_id=account.id,
        token_hash="hash",
        ip_address=None,
        user_agent=None,
        now=NOW,
        expires_at=NOW,
    )
    await fake_sessions.save(session)

    updated = await admin_use_cases.change_user_status(
        target_account_id=account.id, action="SUSPEND", reason="policy violation", now=NOW
    )
    assert updated.status is AccountStatus.SUSPENDED
    assert await fake_sessions.get_by_id(session.id) is None
    assert any(e.event_type == "AccountSuspended" for e in fake_outbox.events)


async def test_change_user_status_reactivate(
    admin_use_cases: AdminIdentityUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    account = _seeded_account().suspend(now=NOW)
    await fake_accounts.add(account)

    updated = await admin_use_cases.change_user_status(
        target_account_id=account.id, action="REACTIVATE", reason=None, now=NOW
    )
    assert updated.status is AccountStatus.ACTIVE


async def test_change_user_status_unknown_account_raises(
    admin_use_cases: AdminIdentityUseCases,
) -> None:
    with pytest.raises(AccountNotFoundError):
        await admin_use_cases.change_user_status(
            target_account_id=UserId(value=uuid4()), action="SUSPEND", reason=None, now=NOW
        )


async def test_list_users_returns_page(
    admin_use_cases: AdminIdentityUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    await fake_accounts.add(_seeded_account())
    await fake_accounts.add(
        UserAccount.register_via_email(
            account_id=UserId(value=uuid4()),
            email=EmailAddress("test@example.com"),
            password_hash="hashed:x",
            display_name=None,
            now=NOW,
        )
    )
    accounts, cursor = await admin_use_cases.list_users(
        status=None, query=None, cursor=None, limit=20
    )
    assert len(accounts) == 2
    assert cursor is None


async def test_assign_role_pins_head_and_version(
    admin_use_cases: AdminIdentityUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_role_reader: FakeRoleDefinitionReader,
) -> None:
    account = _seeded_account()
    await fake_accounts.add(account)
    resolved = fake_role_reader.register_role("administrator", frozenset({"identity:role:assign"}))

    updated = await admin_use_cases.assign_role(
        actor_id=UserId(value=uuid4()),
        target_account_id=account.id,
        role_code="administrator",
        acting_profile_id=None,
        now=NOW,
    )
    assert len(updated.role_assignments) == 1
    assignment = updated.role_assignments[0]
    assert assignment.role_definition_head_id == resolved.head_id
    assert assignment.role_definition_version_id == resolved.version_id


async def test_assign_role_unknown_code_raises(
    admin_use_cases: AdminIdentityUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    account = _seeded_account()
    await fake_accounts.add(account)
    with pytest.raises(RoleDefinitionNotFoundError):
        await admin_use_cases.assign_role(
            actor_id=UserId(value=uuid4()),
            target_account_id=account.id,
            role_code="does-not-exist",
            acting_profile_id=None,
            now=NOW,
        )


async def test_revoke_role_removes_assignment(
    admin_use_cases: AdminIdentityUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_role_reader: FakeRoleDefinitionReader,
) -> None:
    account = _seeded_account()
    await fake_accounts.add(account)
    fake_role_reader.register_role("administrator", frozenset({"identity:role:assign"}))
    assigned = await admin_use_cases.assign_role(
        actor_id=UserId(value=uuid4()),
        target_account_id=account.id,
        role_code="administrator",
        acting_profile_id=None,
        now=NOW,
    )
    head_id = assigned.role_assignments[0].role_definition_head_id

    updated = await admin_use_cases.revoke_role(
        target_account_id=account.id,
        role_definition_head_id=head_id,
        acting_profile_id=None,
        now=NOW,
    )
    assert updated.role_assignments == ()


async def test_revoke_role_not_assigned_raises(
    admin_use_cases: AdminIdentityUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    account = _seeded_account()
    await fake_accounts.add(account)
    with pytest.raises(RoleNotAssignedError):
        await admin_use_cases.revoke_role(
            target_account_id=account.id,
            role_definition_head_id=uuid4(),
            acting_profile_id=None,
            now=NOW,
        )
