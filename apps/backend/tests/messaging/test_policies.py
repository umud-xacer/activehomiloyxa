"""`messaging.domain.policies.MessageRateLimitPolicy` -- BR-MSG-03."""

from __future__ import annotations

import pytest

from messaging.domain import (
    MESSAGE_RATE_LIMIT_MAX_PER_WINDOW,
    MessageRateLimitPolicy,
    RateLimitExceededError,
)


class TestMessageRateLimitPolicy:
    def test_below_the_limit_is_allowed(self) -> None:
        MessageRateLimitPolicy().check(recent_message_count=MESSAGE_RATE_LIMIT_MAX_PER_WINDOW - 1)

    def test_at_the_limit_raises(self) -> None:
        with pytest.raises(RateLimitExceededError):
            MessageRateLimitPolicy().check(recent_message_count=MESSAGE_RATE_LIMIT_MAX_PER_WINDOW)

    def test_over_the_limit_raises(self) -> None:
        with pytest.raises(RateLimitExceededError):
            MessageRateLimitPolicy().check(
                recent_message_count=MESSAGE_RATE_LIMIT_MAX_PER_WINDOW + 5
            )

    def test_exception_carries_retry_after_seconds(self) -> None:
        with pytest.raises(RateLimitExceededError) as exc_info:
            MessageRateLimitPolicy().check(recent_message_count=MESSAGE_RATE_LIMIT_MAX_PER_WINDOW)
        assert exc_info.value.retry_after_seconds > 0
