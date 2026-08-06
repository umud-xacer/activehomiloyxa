"""PII test (Task P-13, Security Sec 12): no message body, phone number, email address, or push
endpoint ever appears in a log record emitted by `NotificationDispatchUseCases`. Captures every
log record emitted during a full queue-then-dispatch cycle (including the fail-closed path) and
asserts none of the PII values used in the fixture data leak into any record's message or
`extra` fields.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from notifications.application.dispatch_use_cases import NotificationDispatchUseCases
from notifications.application.ports import (
    NotificationTemplateSnapshot,
    RecipientSnapshot,
)
from shared_kernel import LocalizedText

from .conftest import (
    FakeEmailProviderPort,
    FakeNotificationRepository,
    FakeSmsProviderPort,
    FakeTemplateReaderPort,
    FakeWebPushProviderPort,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

_EMAIL = "sensitive.person@example.com"
_PHONE = "+998901112233"
_BODY = "Your secret listing details and message content"
_SUBJECT = "Confidential subject line"


def _record_text(record: logging.LogRecord) -> str:
    parts = [record.getMessage()]
    for key, value in vars(record).items():
        if key not in logging.LogRecord("", 0, "", 0, "", (), None).__dict__:
            parts.append(f"{key}={value}")
    return " ".join(parts)


@pytest.mark.asyncio
async def test_no_pii_appears_in_any_log_record_across_success_and_failure_paths(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_notifications = FakeNotificationRepository()
    fake_templates = FakeTemplateReaderPort()
    fake_templates.seed(
        "UserRegistered",
        NotificationTemplateSnapshot(
            template_id=uuid4(),
            template_version_id=uuid4(),
            event_key="UserRegistered",
            channel="EMAIL",
            subject=LocalizedText(uz_latn=_SUBJECT),
            body=LocalizedText(uz_latn=_BODY),
        ),
    )
    recipient = RecipientSnapshot(
        user_id=uuid4(),
        email=_EMAIL,
        phone=_PHONE,
        web_push_subscription=None,
        email_enabled=True,
        web_push_enabled=True,
        sms_enabled=True,
    )

    # Some other test in the full suite (a third-party dependency's own `logging.config.
    # dictConfig` call, outside this module's control) can leave this named logger's own
    # `.disabled` flag set to `True` for the rest of the process -- reset it so this test's own
    # result never depends on suite ordering elsewhere.
    target_logger = logging.getLogger("notifications.application.dispatch_use_cases")
    target_logger.disabled = False

    with caplog.at_level(logging.DEBUG, logger="notifications.application.dispatch_use_cases"):
        # success path
        ok_use_cases = NotificationDispatchUseCases(
            notifications=fake_notifications,
            templates=fake_templates,
            email=FakeEmailProviderPort(),
            sms=FakeSmsProviderPort(),
            web_push=FakeWebPushProviderPort(),
        )
        queued = await ok_use_cases.queue_for_event(
            event_key="UserRegistered", recipient=recipient, now=NOW
        )
        await ok_use_cases.dispatch_queued(queued[0], now=NOW)

        # failure path (fails closed, still must not log PII)
        failing_use_cases = NotificationDispatchUseCases(
            notifications=fake_notifications,
            templates=fake_templates,
            email=FakeEmailProviderPort(fail=True),
            sms=FakeSmsProviderPort(),
            web_push=FakeWebPushProviderPort(),
        )
        queued_2 = await failing_use_cases.queue_for_event(
            event_key="UserRegistered", recipient=recipient, now=NOW
        )
        await failing_use_cases.dispatch_queued(queued_2[0], now=NOW)

    assert len(caplog.records) >= 1, "expected the fail-closed path to log a warning"
    for record in caplog.records:
        text = _record_text(record)
        assert _EMAIL not in text
        assert _PHONE not in text
        assert _BODY not in text
        assert _SUBJECT not in text
