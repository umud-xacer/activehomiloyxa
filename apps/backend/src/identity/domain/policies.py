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

from identity.domain.exceptions import OtpThrottledError

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


class SessionExpiryPolicy:
    """Security Sec 3.2: sessions carry an absolute lifetime, no refresh tokens (SDR-01).
    `session_expiry_hours` is read from configuration's `platform-settings-global` at the
    application layer and passed in here -- this policy performs no I/O of its own."""

    @staticmethod
    def compute_expiry(*, now: datetime, session_expiry_hours: int) -> datetime:
        return now + timedelta(hours=session_expiry_hours)
