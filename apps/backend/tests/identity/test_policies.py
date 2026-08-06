"""Unit tests for `identity.domain.policies` (OtpThrottlePolicy, SessionExpiryPolicy)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from identity.domain import OtpThrottledError, OtpThrottlePolicy, SessionExpiryPolicy

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def test_otp_throttle_policy_allows_when_under_limit() -> None:
    policy = OtpThrottlePolicy(max_requests_per_window=3, window_minutes=15)
    policy.check(recent_requests_by_phone=2, recent_requests_by_ip=2)  # does not raise


def test_I_otp_throttle_denies_when_phone_request_count_at_limit() -> None:
    """P-05 "dedicated ... throttle test" (NFR-SEC-004)."""
    policy = OtpThrottlePolicy(max_requests_per_window=3, window_minutes=15)
    with pytest.raises(OtpThrottledError) as exc_info:
        policy.check(recent_requests_by_phone=3, recent_requests_by_ip=0)
    assert exc_info.value.retry_after_seconds == 15 * 60


def test_otp_throttle_denies_when_ip_request_count_at_limit() -> None:
    policy = OtpThrottlePolicy(max_requests_per_window=3, window_minutes=15)
    with pytest.raises(OtpThrottledError):
        policy.check(recent_requests_by_phone=0, recent_requests_by_ip=3)


def test_session_expiry_policy_computes_expiry_from_hours() -> None:
    expiry = SessionExpiryPolicy.compute_expiry(now=NOW, session_expiry_hours=720)
    assert expiry == NOW + timedelta(hours=720)
