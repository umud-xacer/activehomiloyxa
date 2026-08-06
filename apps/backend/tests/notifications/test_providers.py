"""Per-channel provider adapter tests (Task P-13), each provider mocked at the wire boundary
(no real network calls) -- proves each adapter dispatches correctly and returns the provider's
own opaque message id, and that a missing credential fails closed at construction time.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import httpx
import pytest

from backbone.persistence.env import MissingInfraConfigError
from notifications.application.ports import WebPushSubscriptionSnapshot
from notifications.infrastructure.providers.email import SmtpEmailProviderAdapter
from notifications.infrastructure.providers.eskiz import EskizSmsProviderAdapter
from notifications.infrastructure.providers.web_push import WebPushProviderAdapter

# --- SMTP email adapter ------------------------------------------------------------------------


def test_email_adapter_fails_closed_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with pytest.raises(MissingInfraConfigError):
        SmtpEmailProviderAdapter()


@pytest.mark.asyncio
async def test_email_adapter_sends_via_smtp_and_returns_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")

    sent_messages: list[EmailMessage] = []

    class _FakeSmtp:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            pass

        def __enter__(self) -> _FakeSmtp:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def starttls(self) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            pass

        def send_message(self, message: EmailMessage) -> None:
            sent_messages.append(message)

    with patch.object(smtplib, "SMTP", _FakeSmtp):
        adapter = SmtpEmailProviderAdapter()
        message_id = await adapter.send_email(
            to_email="recipient@example.com", subject="Hi", body="Body text"
        )

    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "recipient@example.com"
    assert sent_messages[0]["Subject"] == "Hi"
    assert message_id  # a Message-ID was generated and returned


# --- Eskiz SMS adapter -------------------------------------------------------------------------


def test_eskiz_adapter_fails_closed_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ESKIZ_API_BASE_URL", raising=False)
    with pytest.raises(MissingInfraConfigError):
        EskizSmsProviderAdapter()


@pytest.mark.asyncio
async def test_eskiz_adapter_sends_sms_and_returns_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESKIZ_API_BASE_URL", "https://eskiz.example.test")
    monkeypatch.setenv("ESKIZ_EMAIL", "test@example.test")
    monkeypatch.setenv("ESKIZ_PASSWORD", "secret")
    monkeypatch.setenv("ESKIZ_SENDER_NICKNAME", "ActiveHome")

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"data": {"token": "fake-token"}})
        if request.url.path == "/message/sms/send":
            return httpx.Response(200, json={"id": "eskiz-msg-42"})
        raise AssertionError(f"unexpected request: {request.url}")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="https://eskiz.example.test"
    )
    adapter = EskizSmsProviderAdapter(client=client)

    message_id = await adapter.send_sms(phone="+998901234567", body="Your listing was suspended")

    assert message_id == "eskiz-msg-42"


# --- web-push adapter --------------------------------------------------------------------------


def test_web_push_adapter_fails_closed_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WEB_PUSH_VAPID_PRIVATE_KEY", raising=False)
    with pytest.raises(MissingInfraConfigError):
        WebPushProviderAdapter()


@pytest.mark.asyncio
async def test_web_push_adapter_sends_and_returns_endpoint_as_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_PUSH_VAPID_PRIVATE_KEY", "fake-vapid-private-key")
    subscription = WebPushSubscriptionSnapshot(
        endpoint="https://push.example.test/abc123",
        p256dh="fake-p256dh",
        auth="fake-auth",
    )

    with patch(
        "notifications.infrastructure.providers.web_push.webpush",
        return_value=MagicMock(),
    ) as mock_webpush:
        adapter = WebPushProviderAdapter()
        message_id = await adapter.send_push(
            subscription=subscription, body="You have a new message"
        )

    assert message_id == subscription.endpoint
    assert mock_webpush.call_count == 1
    _, kwargs = mock_webpush.call_args
    assert kwargs["subscription_info"]["endpoint"] == subscription.endpoint
    assert kwargs["data"] == "You have a new message"
