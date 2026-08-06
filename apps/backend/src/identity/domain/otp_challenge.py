"""identity -- the OtpChallenge aggregate (DDD Sec 5.1: "Short-lived; ... Enforces single-use
and expiry"). The code itself is never stored in the clear (`code_hash` only, Security Sec 3.1
"stored hashed") and never appears in a log message (backbone's redaction filter only scrubs
structured `extra=` keys, not interpolated text -- see identity/README.md)."""

from __future__ import annotations

import hmac
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from identity.domain.exceptions import (
    OtpAlreadyConsumedError,
    OtpAttemptsExceededError,
    OtpExpiredError,
)
from identity.domain.policies import OTP_MAX_VERIFY_ATTEMPTS
from identity.domain.value_objects import OtpPurpose, PhoneNumber


@dataclass(frozen=True)
class OtpChallenge:
    """DDD Sec 5.1 aggregate root `OtpChallenge [P]`."""

    id: UUID
    phone: PhoneNumber
    purpose: OtpPurpose
    code_hash: str
    attempts: int
    max_attempts: int
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    @staticmethod
    def issue(
        *,
        challenge_id: UUID,
        phone: PhoneNumber,
        purpose: OtpPurpose,
        code_hash: str,
        now: datetime,
        expiry_minutes: int,
        max_attempts: int = OTP_MAX_VERIFY_ATTEMPTS,
    ) -> OtpChallenge:
        """`expiry_minutes` is read by the caller from configuration's
        `platform-settings-global.otp.expiry_minutes` (DEC-21: never hardcode a configurable
        value)."""
        return OtpChallenge(
            id=challenge_id,
            phone=phone,
            purpose=purpose,
            code_hash=code_hash,
            attempts=0,
            max_attempts=max_attempts,
            created_at=now,
            expires_at=now + timedelta(minutes=expiry_minutes),
        )

    def verify(self, *, candidate_code_hash: str, now: datetime) -> OtpVerificationOutcome:
        """Returns the state to persist either way -- a mismatch must still increment the
        attempt counter, so the caller persists `.outcome.challenge` unconditionally and only
        raises `OtpCodeMismatchError` itself when `.matched` is `False` (see docstring on
        `OtpVerificationOutcome`). Already-consumed / expired / attempts-exhausted raise
        immediately: there is no state left to mutate in any of those cases."""
        if self.consumed_at is not None:
            raise OtpAlreadyConsumedError()
        if now >= self.expires_at:
            raise OtpExpiredError()
        if self.attempts >= self.max_attempts:
            raise OtpAttemptsExceededError()
        if hmac.compare_digest(candidate_code_hash, self.code_hash):
            return OtpVerificationOutcome(challenge=replace(self, consumed_at=now), matched=True)
        return OtpVerificationOutcome(
            challenge=replace(self, attempts=self.attempts + 1), matched=False
        )


@dataclass(frozen=True)
class OtpVerificationOutcome:
    """Result of `OtpChallenge.verify`. `challenge` is always the new state to persist -- even on
    a mismatch, since the incremented attempt counter must survive the failed attempt (that is
    the entire mechanism behind `OtpAttemptsExceededError`/lockout). `matched` tells the
    application-layer use case whether to raise `OtpCodeMismatchError` after persisting it."""

    challenge: OtpChallenge
    matched: bool
