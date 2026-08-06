"""Unit tests for `AccountUseCases` (FR-USER-001..003, FR-USER-005) against in-memory fakes."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from identity.application import AccountNotFoundError, AccountUseCases, SessionNotFoundError
from identity.domain import (
    AccountStatus,
    DuplicateContactError,
    EmailAddress,
    InvalidCredentialsError,
    NotificationPreferences,
    PhoneNumber,
    PhoneRevealMode,
    PrivacySettings,
    ProfileNotOwnedError,
    Session,
    UnknownAuthenticationMethodError,
    UserAccount,
)
from shared_kernel import BusinessProfileId, UserId

from .conftest import FakeOutbox, FakeSessionRepository, FakeUserAccountRepository

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _seeded_email_account() -> UserAccount:
    return UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("test@example.com"),
        password_hash="hashed:s3cret123",
        display_name="Test User",
        now=NOW,
    )


async def _seed(fake_accounts: FakeUserAccountRepository, account: UserAccount) -> UserAccount:
    await fake_accounts.add(account)
    return account


async def test_get_me_returns_account(
    account_use_cases: AccountUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    account = await _seed(fake_accounts, _seeded_email_account())
    fetched = await account_use_cases.get_me(account.id)
    assert fetched.id == account.id


async def test_get_me_unknown_account_raises(account_use_cases: AccountUseCases) -> None:
    with pytest.raises(AccountNotFoundError):
        await account_use_cases.get_me(UserId(value=uuid4()))


async def test_update_me_changes_display_name(
    account_use_cases: AccountUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    account = await _seed(fake_accounts, _seeded_email_account())
    updated = await account_use_cases.update_me(
        account.id, display_name="New Name", email=None, now=NOW
    )
    assert updated.display_name == "New Name"


async def test_update_me_email_collision_raises_duplicate(
    account_use_cases: AccountUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    other = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("taken@example.com"),
        password_hash="hashed:x",
        display_name=None,
        now=NOW,
    )
    await _seed(fake_accounts, other)
    account = await _seed(fake_accounts, _seeded_email_account())

    with pytest.raises(DuplicateContactError):
        await account_use_cases.update_me(
            account.id, display_name=None, email=EmailAddress("taken@example.com"), now=NOW
        )


async def test_change_password_success_revokes_all_sessions(
    account_use_cases: AccountUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
) -> None:
    account = await _seed(fake_accounts, _seeded_email_account())
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

    await account_use_cases.change_password(
        account.id, current_password="s3cret123", new_password="newpassword", now=NOW
    )
    assert await fake_sessions.get_by_id(session.id) is None


async def test_change_password_wrong_current_password_raises(
    account_use_cases: AccountUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    account = await _seed(fake_accounts, _seeded_email_account())
    with pytest.raises(InvalidCredentialsError):
        await account_use_cases.change_password(
            account.id, current_password="wrong", new_password="newpassword", now=NOW
        )


async def test_change_password_no_email_method_raises(
    account_use_cases: AccountUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    account = await _seed(
        fake_accounts,
        UserAccount.register_via_phone(
            account_id=UserId(value=uuid4()), phone=PhoneNumber("+998901234567"), now=NOW
        ),
    )
    with pytest.raises(UnknownAuthenticationMethodError):
        await account_use_cases.change_password(
            account.id, current_password="x", new_password="y", now=NOW
        )


async def test_update_preferences_changes_privacy_and_notifications(
    account_use_cases: AccountUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    account = await _seed(fake_accounts, _seeded_email_account())
    updated = await account_use_cases.update_preferences(
        account.id,
        privacy_settings=PrivacySettings(phone_reveal_mode=PhoneRevealMode.NEVER),
        notification_preferences=NotificationPreferences(email=False, web_push=True, sms=True),
        now=NOW,
    )
    assert updated.privacy_settings.phone_reveal_mode is PhoneRevealMode.NEVER
    assert updated.notification_preferences.web_push is True


async def test_close_account_anonymises_and_revokes_sessions(
    account_use_cases: AccountUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_outbox: FakeOutbox,
) -> None:
    account = await _seed(fake_accounts, _seeded_email_account())
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

    await account_use_cases.close_account(account.id, now=NOW)

    closed = await fake_accounts.get_by_id(account.id)
    assert closed is not None
    assert closed.status is AccountStatus.CLOSED
    assert await fake_sessions.get_by_id(session.id) is None
    assert any(e.event_type == "AccountClosed" for e in fake_outbox.events)


async def test_list_sessions_returns_only_this_accounts_sessions(
    account_use_cases: AccountUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
) -> None:
    account = await _seed(fake_accounts, _seeded_email_account())
    other_account_id = UserId(value=uuid4())
    mine = Session.issue(
        session_id=uuid4(),
        account_id=account.id,
        token_hash="mine",
        ip_address=None,
        user_agent=None,
        now=NOW,
        expires_at=NOW,
    )
    theirs = Session.issue(
        session_id=uuid4(),
        account_id=other_account_id,
        token_hash="theirs",
        ip_address=None,
        user_agent=None,
        now=NOW,
        expires_at=NOW,
    )
    await fake_sessions.save(mine)
    await fake_sessions.save(theirs)

    sessions = await account_use_cases.list_sessions(account.id)
    assert [s.id for s in sessions] == [mine.id]


async def test_revoke_session_of_another_account_raises_not_found(
    account_use_cases: AccountUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
) -> None:
    account = await _seed(fake_accounts, _seeded_email_account())
    other_account_id = UserId(value=uuid4())
    theirs = Session.issue(
        session_id=uuid4(),
        account_id=other_account_id,
        token_hash="theirs",
        ip_address=None,
        user_agent=None,
        now=NOW,
        expires_at=NOW,
    )
    await fake_sessions.save(theirs)

    with pytest.raises(SessionNotFoundError):
        await account_use_cases.revoke_session(account.id, theirs.id)


async def test_switch_acting_profile_to_owned_profile_succeeds(
    account_use_cases: AccountUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
) -> None:
    profile = BusinessProfileId(value=uuid4())
    account = replace(_seeded_email_account(), owned_profile_ids=(profile,))
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

    updated = await account_use_cases.switch_acting_profile(
        account.id, session.id, new_acting_profile_id=profile, now=NOW
    )
    assert updated.acting_profile_id == profile


async def test_switch_acting_profile_to_unowned_profile_raises(
    account_use_cases: AccountUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
) -> None:
    account = await _seed(fake_accounts, _seeded_email_account())
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

    with pytest.raises(ProfileNotOwnedError):
        await account_use_cases.switch_acting_profile(
            account.id, session.id, new_acting_profile_id=BusinessProfileId(value=uuid4()), now=NOW
        )
