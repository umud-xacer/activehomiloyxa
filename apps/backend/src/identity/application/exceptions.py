"""identity/application -- exceptions for facts the domain layer cannot know (missing rows,
unresolvable cross-module references). Mirrors `configuration.application.exceptions`'s style."""

from __future__ import annotations

from uuid import UUID


class IdentityApplicationError(Exception):
    """Base for every typed exception raised by identity's application/ layer."""


class AccountNotFoundError(IdentityApplicationError):
    def __init__(self, account_id: UUID) -> None:
        self.account_id = account_id
        super().__init__(f"account {account_id} not found")


class SessionNotFoundError(IdentityApplicationError):
    def __init__(self, session_id: UUID) -> None:
        self.session_id = session_id
        super().__init__(f"session {session_id} not found")


class InvalidSessionTokenError(IdentityApplicationError):
    """The presented session token/cookie does not resolve to any stored session (Security Sec
    4.2 Gate 1: no valid session -> 401 AUTHENTICATION_REQUIRED). Distinct from
    `SessionNotFoundError`, which is a 404 for a *known* session id (e.g. `revokeSession`'s path
    parameter) that does not exist or is not owned by the caller."""


class OtpChallengeNotFoundError(IdentityApplicationError):
    """No active (unexpired, unconsumed) OTP challenge exists for this phone/purpose -- verify
    was attempted with no matching `requestOtp` call."""


class InvalidGoogleCredentialError(IdentityApplicationError):
    """The Google authorization code could not be exchanged, or the resulting identity's email
    is not verified (Security Sec 3.1: "email-verified claim required before linking")."""


class InvalidAppleCredentialError(IdentityApplicationError):
    """The Apple authorization code could not be exchanged, the id_token failed signature/claim
    verification, or the resulting identity's email is not verified -- mirrors
    `InvalidGoogleCredentialError`."""


class RoleDefinitionNotFoundError(IdentityApplicationError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"no published role-definition with code {code!r}")


class RecoveryTargetRequiredError(IdentityApplicationError):
    """`startRecovery` requires at least one of phone/email (`RecoveryStartRequest` makes both
    optional at the schema level; the "at least one" rule is a business rule, not a structural
    one, so it is enforced here rather than at the DTO)."""


class OtpProviderUnavailableError(IdentityApplicationError):
    """UNF-032: the SMS provider (Eskiz, DEC-18) could not be reached or rejected the request --
    a degraded external dependency, not an error in this app. `OtpSmsProviderPort` implementations
    raise this instead of letting a provider-SDK exception (e.g. `httpx.HTTPError`) cross the port
    boundary; `interfaces/` maps it to 503, mirroring how `/ready` already reports a down
    dependency instead of pretending the app itself is broken (a plain 500 "Internal server
    error", the previous behaviour, told every caller the wrong thing to fix)."""
