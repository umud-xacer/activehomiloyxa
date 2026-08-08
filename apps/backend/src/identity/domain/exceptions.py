"""identity -- typed domain exceptions, one per invariant violated (Playbook Sec 6: typed domain
exceptions named for the invariant they protect). `interfaces/errors.py` maps each of these to a
`contracts.errors.Problem` (closed `ErrorCode` vocabulary).
"""

from __future__ import annotations

from uuid import UUID


class IdentityDomainError(Exception):
    """Base for every typed exception raised by identity's domain/ layer."""


# --- UserAccount lifecycle -------------------------------------------------------------------


class IllegalAccountStateTransitionError(IdentityDomainError):
    """Attempted an `AccountStatus` transition outside Active<->Suspended->Closed (DDD Sec 5.1)."""

    def __init__(self, current: str, attempted: str) -> None:
        self.current = current
        self.attempted = attempted
        super().__init__(f"cannot transition account from {current} to {attempted}")


class DuplicateContactError(IdentityDomainError):
    """I-09: a UserAccount's phone and email are unique platform-wide."""

    def __init__(self, field: str, value: str) -> None:
        self.field = field
        self.value = value
        super().__init__(f"{field} {value!r} is already registered")


class UnknownAuthenticationMethodError(IdentityDomainError):
    """The account has no authentication method of the requested kind."""

    def __init__(self, method_type: str) -> None:
        self.method_type = method_type
        super().__init__(f"account has no {method_type} authentication method")


class InvalidCredentialsError(IdentityDomainError):
    """Generic invalid-credentials outcome for any authentication method. Deliberately reveals
    nothing about *which* part was wrong or whether the identifier is registered (Security Sec
    3.1: "uniform responses that do not reveal whether a phone is registered")."""


class AccountNotActiveError(IdentityDomainError):
    """Authentication succeeded but the account is not ACTIVE (Suspended/Closed accounts cannot
    establish a new session)."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"account is {status}, not ACTIVE")


class LoginLockedOutError(IdentityDomainError):
    """Security Sec 3.1 brute-force protection: too many consecutive failed `loginEmail` attempts
    against this IP or this account within the lockout window (`LoginLockoutPolicy`). `scope`
    ("ip"/"account") is carried only for logging -- the HTTP response is identical either way
    (Security Sec 3.1's own enumeration-safety reasoning: an attacker probing which scope tripped
    would itself be information leakage)."""

    def __init__(self, retry_after_seconds: int, scope: str) -> None:
        self.retry_after_seconds = retry_after_seconds
        self.scope = scope
        super().__init__(f"login locked out ({scope}), retry after {retry_after_seconds}s")


# --- OtpChallenge (FR-AUTH-001 acceptance criteria) -------------------------------------------


class OtpExpiredError(IdentityDomainError):
    """The OTP challenge's expiry has passed."""


class OtpAlreadyConsumedError(IdentityDomainError):
    """The OTP challenge was already successfully verified once (single-use)."""


class OtpCodeMismatchError(IdentityDomainError):
    """The supplied code does not match the challenge's hashed code."""


class OtpAttemptsExceededError(IdentityDomainError):
    """The challenge's max verify-attempt count has been reached (lockout)."""


class OtpPurposeMismatchError(IdentityDomainError):
    """The code verified successfully but the purpose cannot be completed: LOGIN/RECOVERY
    against a phone with no registered account (FR-AUTH-004 requires an already-registered
    user). Kept distinct from `InvalidCredentialsError` because `verifyOtp` has no 401 response
    in contracts/openapi.yaml (only 200/422/429) -- this maps to 422, `InvalidCredentialsError`
    maps to 401 for `loginEmail`/`loginGoogle`, which do declare one."""


class OtpThrottledError(IdentityDomainError):
    """NFR-SEC-004: too many OTP requests for this phone/IP within the throttle window."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"OTP requests throttled, retry after {retry_after_seconds}s")


# --- Session -------------------------------------------------------------------------------


class SessionExpiredError(IdentityDomainError):
    """The session's absolute lifetime has elapsed (Security Sec 3.2 SessionExpiryPolicy)."""


class SessionRevokedError(IdentityDomainError):
    """The session was explicitly revoked (logout, password change, suspension)."""


# --- Authorization (Security Sec 4.2 four-gate model; I-10, I-11) -----------------------------


class PermissionDeniedError(IdentityDomainError):
    """Gate 3 failure: default-deny -- the required PermissionKey is absent from the acting
    identity's flattened permission set (Security Sec 4.2, I-11). Absence of an explicit grant
    is itself the deny outcome; there is no separate "not found" branch that could accidentally
    fall through to allow."""

    def __init__(self, required_permission: str) -> None:
        self.required_permission = required_permission
        super().__init__(f"permission {required_permission!r} not held")


class WrongActingProfileError(IdentityDomainError):
    """Gate 2/4 failure: I-10 per-acting-profile scoping -- a permission held under one acting
    profile must not leak into another, and cross-profile/cross-owner access is denied by
    default."""

    def __init__(self, acting_profile_id: UUID | None, target_profile_id: UUID | None) -> None:
        self.acting_profile_id = acting_profile_id
        self.target_profile_id = target_profile_id
        super().__init__(
            f"acting profile {acting_profile_id} is not authorized for scope {target_profile_id}"
        )


class ProfileNotOwnedError(IdentityDomainError):
    """Raised when switching to an acting profile the account does not own (FR-USER-002)."""

    def __init__(self, profile_id: UUID) -> None:
        self.profile_id = profile_id
        super().__init__(f"profile {profile_id} is not owned by this account")


class RoleNotAssignedError(IdentityDomainError):
    """Raised when revoking a role the account does not currently hold in the given scope."""

    def __init__(self, role_definition_head_id: UUID) -> None:
        self.role_definition_head_id = role_definition_head_id
        super().__init__(f"role {role_definition_head_id} is not assigned to this account")


# --- Registration review (ADR-0007) -----------------------------------------------------------


class RegistrationAlreadyDecidedError(IdentityDomainError):
    """Attempted to decide a registration review that is not `PENDING` -- APPROVED/REJECTED are
    terminal (mirrors `profiles.domain.exceptions`'s equivalent verification-case guard)."""

    def __init__(self, account_id: UUID, current: str) -> None:
        self.account_id = account_id
        self.current = current
        super().__init__(f"account {account_id} registration review is already {current}")
