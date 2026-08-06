"""Unit tests for the concrete adapters behind identity's two PUBLIC in-process ports
(`AuthorizationPort`, `ContactPolicyPort`) -- what every future module's own DI will receive."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from identity.application.authorization_service import ApplicationAuthorizationService
from identity.domain import (
    EmailAddress,
    PermissionDeniedError,
    PhoneNumber,
    PhoneRevealMode,
    PrivacySettings,
    Session,
    UserAccount,
)
from identity.infrastructure.public_port_adapters import (
    AuthorizationPortAdapter,
    ContactPolicyPortAdapter,
)
from shared_kernel import UserId

from .conftest import (
    FakeRoleDefinitionReader,
    FakeSessionRepository,
    FakeSessionTokenGenerator,
    FakeUserAccountRepository,
)

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _seeded_account() -> UserAccount:
    return UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()), phone=PhoneNumber("+998901234567"), now=NOW
    )


@pytest.fixture
def token_generator() -> FakeSessionTokenGenerator:
    return FakeSessionTokenGenerator()


@pytest.fixture
def authorization_port(
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_role_reader: FakeRoleDefinitionReader,
    token_generator: FakeSessionTokenGenerator,
) -> AuthorizationPortAdapter:
    authz_service = ApplicationAuthorizationService(
        session_repo=fake_sessions, account_repo=fake_accounts, role_reader=fake_role_reader
    )
    return AuthorizationPortAdapter(
        authorization_service=authz_service, token_generator=token_generator
    )


async def _seed_session_for_raw_token(
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    token_generator: FakeSessionTokenGenerator,
    account: UserAccount,
    raw_token: str,
) -> Session:
    await fake_accounts.add(account)
    session = Session.issue(
        session_id=uuid4(),
        account_id=account.id,
        token_hash=token_generator.hash_token(raw_token),
        ip_address=None,
        user_agent=None,
        now=NOW,
        # `AuthorizationPortAdapter` always resolves against real wall-clock time (it has no
        # `now` parameter of its own -- see its docstring), so the expiry must be in the real
        # future regardless of the fixed `NOW` constant used elsewhere in this file.
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await fake_sessions.save(session)
    return session


async def test_authorize_hashes_raw_token_and_returns_account_id(
    authorization_port: AuthorizationPortAdapter,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_role_reader: FakeRoleDefinitionReader,
    token_generator: FakeSessionTokenGenerator,
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
    raw_token = "raw-session-token"
    await _seed_session_for_raw_token(
        fake_accounts, fake_sessions, token_generator, account, raw_token
    )

    account_id = await authorization_port.authorize(
        session_token=raw_token, required_permission="identity:role:assign"
    )
    assert account_id == account.id


async def test_authorize_denies_without_permission(
    authorization_port: AuthorizationPortAdapter,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    token_generator: FakeSessionTokenGenerator,
) -> None:
    account = _seeded_account()
    raw_token = "raw-session-token"
    await _seed_session_for_raw_token(
        fake_accounts, fake_sessions, token_generator, account, raw_token
    )

    with pytest.raises(PermissionDeniedError):
        await authorization_port.authorize(
            session_token=raw_token, required_permission="identity:role:assign"
        )


async def test_get_effective_permissions_returns_flattened_set(
    authorization_port: AuthorizationPortAdapter,
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_role_reader: FakeRoleDefinitionReader,
    token_generator: FakeSessionTokenGenerator,
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
    raw_token = "raw-session-token"
    await _seed_session_for_raw_token(
        fake_accounts, fake_sessions, token_generator, account, raw_token
    )

    permissions = await authorization_port.get_effective_permissions(session_token=raw_token)
    assert permissions == frozenset({"identity:role:assign"})


async def test_contact_policy_returns_configured_phone_reveal_mode(
    fake_accounts: FakeUserAccountRepository,
) -> None:
    account = _seeded_account().update_preferences(
        privacy_settings=PrivacySettings(phone_reveal_mode=PhoneRevealMode.NEVER),
        notification_preferences=None,
        now=NOW,
    )
    await fake_accounts.add(account)

    adapter = ContactPolicyPortAdapter(fake_accounts)
    mode = await adapter.get_phone_reveal_mode(account.id)
    assert mode == "NEVER"


async def test_contact_policy_unknown_account_fails_closed(
    fake_accounts: FakeUserAccountRepository,
) -> None:
    adapter = ContactPolicyPortAdapter(fake_accounts)
    mode = await adapter.get_phone_reveal_mode(UserId(value=uuid4()))
    assert mode == "NEVER"


async def test_reveal_phone_returns_the_number_when_mode_permits(
    fake_accounts: FakeUserAccountRepository,
) -> None:
    account = _seeded_account()  # default PrivacySettings.phone_reveal_mode is ON_REQUEST
    await fake_accounts.add(account)

    adapter = ContactPolicyPortAdapter(fake_accounts)
    phone = await adapter.reveal_phone(account.id)
    assert phone == "+998901234567"


async def test_reveal_phone_returns_none_when_mode_is_never(
    fake_accounts: FakeUserAccountRepository,
) -> None:
    account = _seeded_account().update_preferences(
        privacy_settings=PrivacySettings(phone_reveal_mode=PhoneRevealMode.NEVER),
        notification_preferences=None,
        now=NOW,
    )
    await fake_accounts.add(account)

    adapter = ContactPolicyPortAdapter(fake_accounts)
    phone = await adapter.reveal_phone(account.id)
    assert phone is None


async def test_reveal_phone_returns_none_when_no_phone_on_file(
    fake_accounts: FakeUserAccountRepository,
) -> None:
    account = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("a@example.com"),
        password_hash="hashed",
        display_name=None,
        now=NOW,
    )
    await fake_accounts.add(account)

    adapter = ContactPolicyPortAdapter(fake_accounts)
    phone = await adapter.reveal_phone(account.id)
    assert phone is None


async def test_reveal_phone_unknown_account_fails_closed(
    fake_accounts: FakeUserAccountRepository,
) -> None:
    adapter = ContactPolicyPortAdapter(fake_accounts)
    phone = await adapter.reveal_phone(UserId(value=uuid4()))
    assert phone is None
