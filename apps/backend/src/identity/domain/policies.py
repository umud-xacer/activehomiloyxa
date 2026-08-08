"""identity -- standalone domain policies (DDD Sec 5.1: OtpThrottlePolicy, SessionExpiryPolicy).
`ProfileScopingPolicy` and `AccountClosurePolicy` are implemented as methods directly on
`Session`/`UserAccount` (their docstrings name the policy) rather than as separate classes here,
since each is a single cohesive state transition with no independent inputs of its own.

Numeric thresholds below are implementation-chosen defaults: NFR-SEC-004 and Security Sec 3.1
only specify qualitative controls ("short expiry", "max attempts then lockout with backoff",
"throttled per-phone and per-IP") -- no literal numbers appear in the approved documents. OTP
*expiry* itself is NOT one of these constants; it is read from configuration's
`platform-settings-global.otp.expiry_minutes` at the application layer (DEC-21: never hardcode a
configurable value) and passed in to `OtpChallenge.issue(...)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from identity.domain.exceptions import LoginLockedOutError, OtpThrottledError

OTP_MAX_REQUESTS_PER_WINDOW = 3
"""Max OTP requests per phone (and, independently, per IP) within the throttle window."""

OTP_THROTTLE_WINDOW_MINUTES = 15

OTP_MAX_VERIFY_ATTEMPTS = 5
"""Max verify attempts against a single challenge before it is locked out (`OtpAttemptsExceededError`)."""


@dataclass(frozen=True)
class OtpThrottlePolicy:
    """NFR-SEC-004: OTP requests are throttled per-phone and per-IP. The calling use case
    resolves the recent-request counts (via `OtpChallengeRepository`) and passes them in; this
    policy makes the pure allow/deny decision."""

    max_requests_per_window: int = OTP_MAX_REQUESTS_PER_WINDOW
    window_minutes: int = OTP_THROTTLE_WINDOW_MINUTES

    def check(self, *, recent_requests_by_phone: int, recent_requests_by_ip: int) -> None:
        if recent_requests_by_phone >= self.max_requests_per_window:
            raise OtpThrottledError(retry_after_seconds=self.window_minutes * 60)
        if recent_requests_by_ip >= self.max_requests_per_window:
            raise OtpThrottledError(retry_after_seconds=self.window_minutes * 60)


@dataclass(frozen=True)
class LoginLockoutPolicy:
    """Security Sec 3.1 brute-force protection: consecutive failed `loginEmail` attempts, tracked
    independently per source IP and per targeted account (`LoginAttemptTrackerPort`, Redis-backed)
    so this policy stays a pure allow/deny decision over a count the calling use case resolves --
    same split as `OtpThrottlePolicy` above. Two independent scopes rather than one: IP-only
    would let one attacker's failures against ONE victim account lock out every other legitimate
    user sharing that IP (NAT/office/campus) from logging into their OWN, unrelated accounts;
    account-only would miss an attacker sweeping many accounts from one IP. Checking both catches
    both attack shapes without either scope's lockout punishing traffic outside it.

    Unlike `OtpThrottlePolicy`'s hardcoded class-default thresholds, `max_attempts`/
    `block_minutes` are always constructed from `platform-settings-global`'s
    `login_lockout.max_attempts`/`login_lockout.block_minutes` (`IdentityPlatformSettings`) --
    admin-tunable without a redeploy, per this feature's own requirement. The same value doubles
    as the failure-counting window: `LoginAttemptTrackerPort.record_failure` re-arms the Redis key
    TTL to `block_minutes` on every failure, so an attacker who pauses between guesses long enough
    for the window to lapse starts counting from zero again -- "consecutive" in the ordinary
    sense, not an unbounded lifetime count."""

    max_attempts: int
    block_minutes: int

    def check_not_locked(self, *, failed_count: int, retry_after_seconds: int, scope: str) -> None:
        if failed_count >= self.max_attempts:
            raise LoginLockedOutError(retry_after_seconds=retry_after_seconds, scope=scope)


class SessionExpiryPolicy:
    """Security Sec 3.2: sessions carry an absolute lifetime, no refresh tokens (SDR-01).
    `session_expiry_hours` is read from configuration's `platform-settings-global` at the
    application layer and passed in here -- this policy performs no I/O of its own."""

    @staticmethod
    def compute_expiry(*, now: datetime, session_expiry_hours: int) -> datetime:
        return now + timedelta(hours=session_expiry_hours)
