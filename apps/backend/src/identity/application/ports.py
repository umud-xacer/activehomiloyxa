"""identity/application -- ports (Task P-05). Abstract surface only (typing.Protocol);
`infrastructure/` implements every one of these, never the reverse (Clean Architecture rule 4).
Provider SDK types (Eskiz, Google) never appear here -- only plain domain/primitive types
(`provider-sdk-confined-to-infrastructure`, tools/importlinter.cfg).
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from identity.domain import (
    EmailAddress,
    OtpChallenge,
    OtpPurpose,
    PhoneNumber,
    Session,
    UserAccount,
)
from shared_kernel import UserId


class UserAccountRepository(Protocol):
    """One repository per aggregate (`UserAccount`, including its `AuthenticationMethod` and
    `RoleAssignment` entities -- Clean Architecture rule 2)."""

    async def get_by_id(self, account_id: UserId) -> UserAccount | None: ...

    async def get_by_phone(self, phone: PhoneNumber) -> UserAccount | None: ...

    async def get_by_email(self, email: EmailAddress) -> UserAccount | None:
        """Also the lookup `loginGoogle` uses to find an existing account to link (I-09: link by
        *verified email*, never by the provider's own subject id -- there is deliberately no
        `get_by_google_subject`)."""
        ...

    async def add(self, account: UserAccount) -> None: ...

    async def save(self, account: UserAccount) -> None: ...

    async def list_page(
        self,
        *,
        status: str | None,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[UserAccount], str | None]:
        """Returns `(accounts, next_cursor)`; `next_cursor` is `None` once exhausted. Backs
        `adminListUsers`."""
        ...

    async def list_pending_review(
        self, *, cursor: str | None, limit: int
    ) -> tuple[list[UserAccount], str | None]:
        """ADR-0007: accounts with `review_status=PENDING`, oldest-first (earliest signups
        reviewed first, mirrors `profiles.VerificationCaseRepository.list_queue`'s FIFO-by-default
        ordering). Backs `listRegistrationQueue`."""
        ...


class SessionRepository(Protocol):
    """Redis-backed (Security Sec 3.2: server-side sessions, no JWT)."""

    async def get_by_id(self, session_id: UUID) -> Session | None: ...

    async def get_by_token_hash(self, token_hash: str) -> Session | None: ...

    async def list_for_account(self, account_id: UserId) -> list[Session]: ...

    async def save(self, session: Session) -> None: ...

    async def delete(self, session_id: UUID) -> None: ...

    async def delete_all_for_account(self, account_id: UserId) -> None:
        """Security Sec 3.3: password change and account suspension trigger bulk session
        revocation server-side, including the session making the request -- the client must
        re-authenticate."""
        ...


class OtpChallengeRepository(Protocol):
    async def get_active_for_phone(
        self, phone: PhoneNumber, purpose: OtpPurpose
    ) -> OtpChallenge | None: ...

    async def add(self, challenge: OtpChallenge, *, ip_address: str) -> None:
        """`ip_address` is persisted alongside the challenge purely to back
        `count_recent_requests_by_ip` -- it is not part of the `OtpChallenge` aggregate itself
        (the domain has no use for it beyond this repository-level throttle query)."""
        ...

    async def save(self, challenge: OtpChallenge) -> None: ...

    async def count_recent_requests_by_phone(self, phone: PhoneNumber, *, since: datetime) -> int:
        """NFR-SEC-004: throttled per-phone."""
        ...

    async def count_recent_requests_by_ip(self, ip_address: str, *, since: datetime) -> int:
        """NFR-SEC-004: throttled per-IP."""
        ...


class OtpSmsProviderPort(Protocol):
    """Eskiz SMS (DEC-18, Baseline Sec 4-A). The only place an Eskiz SDK type may appear is the
    concrete `infrastructure/` adapter implementing this Protocol."""

    async def send_otp(self, *, phone: PhoneNumber, code: str) -> None: ...


class OtpChallengeUnitOfWork(Protocol):
    """P-21 fix (confirmed integration defect, Playbook Sec 6: "a transaction is never held open
    across a provider port call"): opens a FRESH, independently-committed transaction for the
    throttle-check + `OtpChallenge` persistence step, separate from `AuthenticationUseCases`' own
    ambient session -- the write must be durably committed and its connection released BEFORE the
    (real, network-bound, up-to-10s-timeout) SMS provider call that follows `request_otp`. Without
    this, every `POST /auth/otp` held a Postgres connection idle for the whole Eskiz round-trip --
    a real connection-pool-exhaustion risk at NFR-SCALE-001's 2,000 concurrent users, since
    registration/login is precisely where concurrent load concentrates."""

    def open(self) -> AbstractAsyncContextManager[OtpChallengeRepository]:
        """Returns an async context manager yielding a repository backed by a brand-new session;
        the transaction commits (or rolls back on exception) when the `with` block exits -- well
        BEFORE the caller goes on to call the SMS provider."""
        ...


class EmailProviderPort(Protocol):
    """Outbound transactional email. `send_email_confirmation`'s token cannot currently be
    consumed by any operation in contracts/openapi.yaml (see `identity/README.md` "Known gaps");
    it is sent for forward-compatibility and audit only. `send_recovery_notice` deliberately
    carries no token/link for the same reason and must read identically whether or not the email
    is registered (FR-AUTH-006, enumeration-safety)."""

    async def send_email_confirmation(self, *, email: EmailAddress, token: str) -> None: ...

    async def send_recovery_notice(self, *, email: EmailAddress) -> None: ...


@dataclass(frozen=True)
class GoogleIdentity:
    """Result of exchanging a Google authorization code -- provider-agnostic, no Google SDK type."""

    subject: str
    email: str
    email_verified: bool
    display_name: str | None


class GoogleOAuthProviderPort(Protocol):
    """DEC-18: Google OAuth behind a provider port. No Google SDK type, and no Google token,
    crosses this boundary outward (Security Sec 3.1: "the Google subject id is an external
    reference held behind the adapter and never exposed")."""

    async def exchange_authorization_code(
        self, *, authorization_code: str, redirect_uri: str
    ) -> GoogleIdentity: ...


class PasswordHasherPort(Protocol):
    """Argon2id (Security Sec 3.1). Domain never sees a plaintext password past this boundary."""

    def hash_password(self, password: str) -> str: ...

    def verify_password(self, *, password: str, password_hash: str) -> bool: ...


class OtpCodeGeneratorPort(Protocol):
    """Generates and hashes the OTP code. A distinct, faster hash than `PasswordHasherPort`
    (short-lived, high-cardinality-enough numeric code, not a user-chosen secret) -- concrete
    adapter uses salted SHA-256, not Argon2id."""

    def generate_code(self) -> str: ...

    def hash_code(self, code: str) -> str: ...


class SessionTokenGeneratorPort(Protocol):
    """Generates the opaque session token and its at-rest hash (Security Sec 3.2
    `identity.session.token_hash`)."""

    def generate_token(self) -> str: ...

    def hash_token(self, token: str) -> str: ...


@dataclass(frozen=True)
class ResolvedRoleDefinition:
    """A published RoleDefinition read from `configuration` via its `interfaces/` package only
    (never `configuration.domain`/`application`/`infrastructure` -- `cross-module-identity`,
    tools/importlinter.cfg). `permission_keys` is the flat set configuration already resolved at
    publish time (Config Framework Sec 7.2); identity never re-flattens it."""

    head_id: UUID
    version_id: UUID
    code: str
    permission_keys: frozenset[str]


class RoleDefinitionReaderPort(Protocol):
    async def resolve_by_code(self, code: str) -> ResolvedRoleDefinition:
        """Looks up the PUBLISHED head+current-version for a role code (e.g. "super-admin").
        Raises `RoleDefinitionNotFoundError` (application/exceptions.py) if no such published
        role exists."""
        ...

    async def get_permission_keys(self, *, head_id: UUID, version_id: UUID) -> frozenset[str]:
        """Re-resolves a `RoleAssignment`'s pinned (head, version) to its permission set. Safe to
        cache indefinitely keyed by `version_id`: published configuration versions are
        immutable."""
        ...


@dataclass(frozen=True)
class IdentityPlatformSettings:
    """The subset of `platform-settings-global` (configuration, seeded in P-04) identity's
    policies read at runtime (DEC-21: never hardcode a configurable value)."""

    otp_expiry_minutes: int
    session_expiry_hours: int


class PlatformSettingsReaderPort(Protocol):
    async def get_identity_settings(self) -> IdentityPlatformSettings: ...
