"""Shared fixtures for `identity`'s fast (no-DB) unit + API tests: in-memory fakes for every
port `application/ports.py` declares, mirroring the real adapters' query semantics closely
enough to exercise use-case behaviour without a real database/Redis. Real-Postgres/Redis
integration tests live under `integration/` with their own `conftest.py`.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from identity.application.ports import (
    GoogleIdentity,
    IdentityPlatformSettings,
    ResolvedRoleDefinition,
)
from identity.domain import (
    EmailAddress,
    OtpChallenge,
    OtpPurpose,
    PhoneNumber,
    RegistrationReviewStatus,
    Session,
    UserAccount,
)
from shared_kernel import EventEnvelope, UserId

if TYPE_CHECKING:
    from identity.application import AccountUseCases, AdminIdentityUseCases, AuthenticationUseCases


@dataclass
class FakeUserAccountRepository:
    """Implements `identity.application.ports.UserAccountRepository`."""

    accounts: dict[UUID, UserAccount] = field(default_factory=dict)

    async def get_by_id(self, account_id: UserId) -> UserAccount | None:
        return self.accounts.get(account_id.value)

    async def get_by_phone(self, phone: PhoneNumber) -> UserAccount | None:
        return next((a for a in self.accounts.values() if a.phone == phone), None)

    async def get_by_email(self, email: EmailAddress) -> UserAccount | None:
        return next((a for a in self.accounts.values() if a.email == email), None)

    async def add(self, account: UserAccount) -> None:
        self.accounts[account.id.value] = account

    async def save(self, account: UserAccount) -> None:
        self.accounts[account.id.value] = account

    async def list_page(
        self, *, status: str | None, query: str | None, cursor: str | None, limit: int
    ) -> tuple[list[UserAccount], str | None]:
        items = sorted(self.accounts.values(), key=lambda a: (a.created_at, str(a.id.value)))
        if status is not None:
            items = [a for a in items if a.status.value == status]
        if query:
            needle = query.lower()
            items = [
                a
                for a in items
                if (a.email and needle in a.email.value)
                or (a.phone and needle in a.phone.value)
                or (a.display_name and needle in a.display_name.lower())
            ]
        page = items[:limit]
        next_cursor = "more" if len(items) > limit else None
        return page, next_cursor

    async def list_pending_review(
        self, *, cursor: str | None, limit: int
    ) -> tuple[list[UserAccount], str | None]:
        items = [
            a for a in self.accounts.values() if a.review_status is RegistrationReviewStatus.PENDING
        ]
        items.sort(key=lambda a: (a.created_at, str(a.id.value)))
        page = items[:limit]
        next_cursor = "more" if len(items) > limit else None
        return page, next_cursor


@dataclass
class FakeSessionRepository:
    """Implements `identity.application.ports.SessionRepository`."""

    by_id: dict[UUID, Session] = field(default_factory=dict)

    async def get_by_id(self, session_id: UUID) -> Session | None:
        return self.by_id.get(session_id)

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        return next((s for s in self.by_id.values() if s.token_hash == token_hash), None)

    async def list_for_account(self, account_id: UserId) -> list[Session]:
        return [s for s in self.by_id.values() if s.account_id == account_id]

    async def save(self, session: Session) -> None:
        self.by_id[session.id] = session

    async def delete(self, session_id: UUID) -> None:
        self.by_id.pop(session_id, None)

    async def delete_all_for_account(self, account_id: UserId) -> None:
        for session_id in [s.id for s in self.by_id.values() if s.account_id == account_id]:
            del self.by_id[session_id]


@dataclass
class FakeOtpChallengeRepository:
    """Implements `identity.application.ports.OtpChallengeRepository`."""

    challenges: dict[UUID, OtpChallenge] = field(default_factory=dict)
    ip_by_challenge: dict[UUID, str] = field(default_factory=dict)

    async def get_active_for_phone(
        self, phone: PhoneNumber, purpose: OtpPurpose
    ) -> OtpChallenge | None:
        candidates = [
            c
            for c in self.challenges.values()
            if c.phone == phone and c.purpose == purpose and c.consumed_at is None
        ]
        return max(candidates, key=lambda c: c.created_at) if candidates else None

    async def add(self, challenge: OtpChallenge, *, ip_address: str) -> None:
        self.challenges[challenge.id] = challenge
        self.ip_by_challenge[challenge.id] = ip_address

    async def save(self, challenge: OtpChallenge) -> None:
        self.challenges[challenge.id] = challenge

    async def count_recent_requests_by_phone(self, phone: PhoneNumber, *, since: datetime) -> int:
        return sum(
            1 for c in self.challenges.values() if c.phone == phone and c.created_at >= since
        )

    async def count_recent_requests_by_ip(self, ip_address: str, *, since: datetime) -> int:
        return sum(
            1
            for cid, ip in self.ip_by_challenge.items()
            if ip == ip_address and self.challenges[cid].created_at >= since
        )


class FakeOtpChallengeUnitOfWork:
    """Implements `identity.application.ports.OtpChallengeUnitOfWork`. No real transaction to
    isolate for an in-memory fake -- just hands back the SAME shared fake repository, so unit
    tests observe the write immediately (`open()` still exists so `request_otp`'s `async with
    self._otp_challenge_unit_of_work.open() as ...:` shape is exercised for real, not bypassed)."""

    def __init__(self, repository: FakeOtpChallengeRepository) -> None:
        self._repository = repository

    @asynccontextmanager
    async def open(self) -> AsyncIterator[FakeOtpChallengeRepository]:
        yield self._repository


class FakeOtpSmsProvider:
    def __init__(self) -> None:
        self.sent: list[tuple[PhoneNumber, str]] = []

    async def send_otp(self, *, phone: PhoneNumber, code: str) -> None:
        self.sent.append((phone, code))


class FakeEmailProvider:
    def __init__(self) -> None:
        self.confirmations: list[tuple[EmailAddress, str]] = []
        self.recovery_notices: list[EmailAddress] = []

    async def send_email_confirmation(self, *, email: EmailAddress, token: str) -> None:
        self.confirmations.append((email, token))

    async def send_recovery_notice(self, *, email: EmailAddress) -> None:
        self.recovery_notices.append(email)


class FakeGoogleOAuthProvider:
    def __init__(self, identity: GoogleIdentity | None = None) -> None:
        self.identity = identity
        self.calls: list[tuple[str, str]] = []

    async def exchange_authorization_code(
        self, *, authorization_code: str, redirect_uri: str
    ) -> GoogleIdentity:
        self.calls.append((authorization_code, redirect_uri))
        if self.identity is None:
            raise AssertionError("FakeGoogleOAuthProvider.identity not configured for this test")
        return self.identity


class FakePasswordHasher:
    """Not real Argon2id -- deterministic and fast, since these are pure application-layer
    unit tests exercising business logic, not the crypto primitive itself (that is exercised by
    `identity.infrastructure.security`'s own tests)."""

    def hash_password(self, password: str) -> str:
        return f"hashed:{password}"

    def verify_password(self, *, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


class FakeOtpCodeGenerator:
    def __init__(self, fixed_code: str = "123456") -> None:
        self.fixed_code = fixed_code

    def generate_code(self) -> str:
        return self.fixed_code

    def hash_code(self, code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()


class FakeSessionTokenGenerator:
    def generate_token(self) -> str:
        return uuid4().hex

    def hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class FakeRoleDefinitionReader:
    """Implements `identity.application.ports.RoleDefinitionReaderPort`."""

    roles_by_code: dict[str, ResolvedRoleDefinition] = field(default_factory=dict)
    permission_keys_by_version: dict[tuple[UUID, UUID], frozenset[str]] = field(
        default_factory=dict
    )

    async def resolve_by_code(self, code: str) -> ResolvedRoleDefinition:
        from identity.application.exceptions import RoleDefinitionNotFoundError

        resolved = self.roles_by_code.get(code)
        if resolved is None:
            raise RoleDefinitionNotFoundError(code)
        return resolved

    async def get_permission_keys(self, *, head_id: UUID, version_id: UUID) -> frozenset[str]:
        return self.permission_keys_by_version.get((head_id, version_id), frozenset())

    def register_role(self, code: str, permission_keys: frozenset[str]) -> ResolvedRoleDefinition:
        resolved = ResolvedRoleDefinition(
            head_id=uuid4(), version_id=uuid4(), code=code, permission_keys=permission_keys
        )
        self.roles_by_code[code] = resolved
        self.permission_keys_by_version[(resolved.head_id, resolved.version_id)] = permission_keys
        return resolved


class FakePlatformSettingsReader:
    def __init__(self, *, otp_expiry_minutes: int = 5, session_expiry_hours: int = 720) -> None:
        self._settings = IdentityPlatformSettings(
            otp_expiry_minutes=otp_expiry_minutes, session_expiry_hours=session_expiry_hours
        )

    async def get_identity_settings(self) -> IdentityPlatformSettings:
        return self._settings


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


@pytest.fixture
def fake_accounts() -> FakeUserAccountRepository:
    return FakeUserAccountRepository()


@pytest.fixture
def fake_sessions() -> FakeSessionRepository:
    return FakeSessionRepository()


@pytest.fixture
def fake_otp_challenges() -> FakeOtpChallengeRepository:
    return FakeOtpChallengeRepository()


@pytest.fixture
def fake_otp_challenge_unit_of_work(
    fake_otp_challenges: FakeOtpChallengeRepository,
) -> FakeOtpChallengeUnitOfWork:
    return FakeOtpChallengeUnitOfWork(fake_otp_challenges)


@pytest.fixture
def fake_outbox() -> FakeOutbox:
    return FakeOutbox()


@pytest.fixture
def fake_role_reader() -> FakeRoleDefinitionReader:
    return FakeRoleDefinitionReader()


@pytest.fixture
def fake_platform_settings() -> FakePlatformSettingsReader:
    return FakePlatformSettingsReader()


@pytest.fixture
def fake_otp_sms_provider() -> FakeOtpSmsProvider:
    return FakeOtpSmsProvider()


@pytest.fixture
def fake_email_provider() -> FakeEmailProvider:
    return FakeEmailProvider()


@pytest.fixture
def fake_google_provider() -> FakeGoogleOAuthProvider:
    return FakeGoogleOAuthProvider()


@pytest.fixture
def auth_use_cases(
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_otp_challenges: FakeOtpChallengeRepository,
    fake_otp_challenge_unit_of_work: FakeOtpChallengeUnitOfWork,
    fake_outbox: FakeOutbox,
    fake_platform_settings: FakePlatformSettingsReader,
    fake_otp_sms_provider: FakeOtpSmsProvider,
    fake_email_provider: FakeEmailProvider,
    fake_google_provider: FakeGoogleOAuthProvider,
) -> AuthenticationUseCases:
    from identity.application import AuthenticationUseCases

    return AuthenticationUseCases(
        accounts=fake_accounts,
        sessions=fake_sessions,
        otp_challenges=fake_otp_challenges,
        otp_challenge_unit_of_work=fake_otp_challenge_unit_of_work,
        outbox=fake_outbox,
        otp_sms_provider=fake_otp_sms_provider,
        email_provider=fake_email_provider,
        google_provider=fake_google_provider,
        password_hasher=FakePasswordHasher(),
        otp_code_generator=FakeOtpCodeGenerator(),
        session_token_generator=FakeSessionTokenGenerator(),
        platform_settings=fake_platform_settings,
    )


@pytest.fixture
def account_use_cases(
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_outbox: FakeOutbox,
) -> AccountUseCases:
    from identity.application import AccountUseCases

    return AccountUseCases(
        accounts=fake_accounts,
        sessions=fake_sessions,
        outbox=fake_outbox,
        password_hasher=FakePasswordHasher(),
    )


@pytest.fixture
def admin_use_cases(
    fake_accounts: FakeUserAccountRepository,
    fake_sessions: FakeSessionRepository,
    fake_outbox: FakeOutbox,
    fake_role_reader: FakeRoleDefinitionReader,
) -> AdminIdentityUseCases:
    from identity.application import AdminIdentityUseCases

    return AdminIdentityUseCases(
        accounts=fake_accounts,
        sessions=fake_sessions,
        outbox=fake_outbox,
        role_reader=fake_role_reader,
    )
