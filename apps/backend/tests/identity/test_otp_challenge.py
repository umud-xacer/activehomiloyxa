"""Unit tests for the `OtpChallenge` aggregate (DDD Sec 5.1; FR-AUTH-001 acceptance): single-use,
expiry, and attempt-lockout enforcement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from identity.domain import (
    OtpAlreadyConsumedError,
    OtpAttemptsExceededError,
    OtpChallenge,
    OtpExpiredError,
    OtpPurpose,
    PhoneNumber,
)

NOW = datetime(2026, 7, 11, tzinfo=UTC)
CODE_HASH = "hash-of-123456"
WRONG_HASH = "hash-of-000000"


def _issue(**overrides: object) -> OtpChallenge:
    defaults: dict[str, object] = {
        "challenge_id": uuid4(),
        "phone": PhoneNumber("+998901234567"),
        "purpose": OtpPurpose.REGISTRATION,
        "code_hash": CODE_HASH,
        "now": NOW,
        "expiry_minutes": 5,
    }
    defaults.update(overrides)
    return OtpChallenge.issue(**defaults)  # type: ignore[arg-type]


def test_issue_sets_expiry_from_expiry_minutes() -> None:
    challenge = _issue(expiry_minutes=5)
    assert challenge.expires_at == NOW + timedelta(minutes=5)
    assert challenge.attempts == 0
    assert challenge.consumed_at is None


def test_verify_correct_code_marks_consumed_and_matched() -> None:
    challenge = _issue()
    outcome = challenge.verify(candidate_code_hash=CODE_HASH, now=NOW)
    assert outcome.matched is True
    assert outcome.challenge.consumed_at == NOW


def test_verify_wrong_code_increments_attempts_and_reports_no_match() -> None:
    challenge = _issue()
    outcome = challenge.verify(candidate_code_hash=WRONG_HASH, now=NOW)
    assert outcome.matched is False
    assert outcome.challenge.attempts == 1
    assert outcome.challenge.consumed_at is None


def test_I_otp_single_use_second_verify_against_consumed_challenge_raises() -> None:
    """FR-AUTH-001 acceptance / P-05 "dedicated single-use-OTP test": a second verify attempt
    with the same (already-consumed) challenge fails, proving single-use is the actual code path
    -- not an accidental side effect of some other check."""
    challenge = _issue()
    outcome = challenge.verify(candidate_code_hash=CODE_HASH, now=NOW)
    assert outcome.matched is True

    with pytest.raises(OtpAlreadyConsumedError):
        outcome.challenge.verify(candidate_code_hash=CODE_HASH, now=NOW)


def test_verify_past_expiry_raises_otp_expired_error() -> None:
    challenge = _issue(expiry_minutes=5)
    with pytest.raises(OtpExpiredError):
        challenge.verify(candidate_code_hash=CODE_HASH, now=NOW + timedelta(minutes=6))


def test_verify_after_max_attempts_raises_attempts_exceeded_error() -> None:
    challenge = _issue(max_attempts=2)
    outcome = challenge.verify(candidate_code_hash=WRONG_HASH, now=NOW)
    outcome = outcome.challenge.verify(candidate_code_hash=WRONG_HASH, now=NOW)
    assert outcome.challenge.attempts == 2

    with pytest.raises(OtpAttemptsExceededError):
        outcome.challenge.verify(candidate_code_hash=CODE_HASH, now=NOW)
