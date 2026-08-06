"""Domain-layer invariant tests for `notifications.domain.notification.Notification` (Task
P-13) -- guarded status transitions, no setters.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from notifications.domain import (
    Channel,
    DeliveryStatus,
    IllegalNotificationStateTransitionError,
    Notification,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _new_notification(**overrides: object) -> Notification:
    defaults: dict[str, object] = {
        "notification_id": uuid4(),
        "recipient_user_id": uuid4(),
        "event_key": "UserRegistered",
        "channel": Channel.EMAIL,
        "template_id": uuid4(),
        "template_version_id": uuid4(),
        "locale": "uz_latn",
        "rendered_subject": "Welcome",
        "rendered_body": "Welcome to Active Home",
        "now": NOW,
    }
    defaults.update(overrides)
    return Notification.create(**defaults)  # type: ignore[arg-type]


def test_create_produces_queued_with_zero_attempts() -> None:
    n = _new_notification()
    assert n.delivery_status is DeliveryStatus.QUEUED
    assert n.attempts == 0
    assert n.provider_message_ref is None
    assert n.sent_at is None
    assert n.read_at is None


def test_mark_sent_from_queued_records_provider_ref_and_bumps_attempts() -> None:
    n = _new_notification()
    sent = n.mark_sent(provider_message_ref="abc123", now=NOW)
    assert sent.delivery_status is DeliveryStatus.SENT
    assert sent.provider_message_ref == "abc123"
    assert sent.attempts == 1
    assert sent.sent_at == NOW


def test_mark_failed_from_queued_records_failure_and_bumps_attempts() -> None:
    n = _new_notification()
    failed = n.mark_failed(now=NOW)
    assert failed.delivery_status is DeliveryStatus.FAILED
    assert failed.attempts == 1
    assert failed.provider_message_ref is None


@pytest.mark.parametrize("outcome", ["sent", "failed"])
def test_mark_sent_or_failed_twice_is_illegal(outcome: str) -> None:
    n = _new_notification()
    once = (
        n.mark_sent(provider_message_ref="x", now=NOW)
        if outcome == "sent"
        else n.mark_failed(now=NOW)
    )
    with pytest.raises(IllegalNotificationStateTransitionError):
        once.mark_sent(provider_message_ref="y", now=NOW)
    with pytest.raises(IllegalNotificationStateTransitionError):
        once.mark_failed(now=NOW)


def test_mark_read_is_independent_of_delivery_status() -> None:
    failed = _new_notification().mark_failed(now=NOW)
    read = failed.mark_read(now=NOW)
    assert read.read_at == NOW
    assert read.delivery_status is DeliveryStatus.FAILED


def test_mark_read_twice_is_idempotent_not_an_error() -> None:
    n = _new_notification()
    once = n.mark_read(now=NOW)
    twice = once.mark_read(now=datetime(2026, 7, 14, tzinfo=UTC))
    assert twice.read_at == NOW  # unchanged, not bumped to the later timestamp
    assert twice is once


def test_mark_unread_clears_read_at() -> None:
    n = _new_notification().mark_read(now=NOW)
    unread = n.mark_unread()
    assert unread.read_at is None


def test_mark_unread_when_already_unread_is_a_noop() -> None:
    n = _new_notification()
    assert n.mark_unread() is n
