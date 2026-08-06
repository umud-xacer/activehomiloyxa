"""UNF-032: `EskizSmsProviderAdapter` must never let an `httpx` exception cross the port
boundary -- `interfaces/` maps `OtpProviderUnavailableError` to 503, not the generic 500 a raw
`httpx.HTTPError` used to fall through to via the catch-all exception handler."""

from __future__ import annotations

import os

import httpx
import pytest

from identity.application.exceptions import OtpProviderUnavailableError
from identity.domain import PhoneNumber
from identity.infrastructure.providers.eskiz import EskizSmsProviderAdapter


@pytest.fixture(autouse=True)
def _eskiz_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ESKIZ_API_BASE_URL", "https://notify.eskiz.uz/api")
    monkeypatch.setenv("ESKIZ_EMAIL", "test@example.com")
    monkeypatch.setenv("ESKIZ_PASSWORD", "test")
    monkeypatch.setenv("ESKIZ_SENDER_NICKNAME", "4546")


def _adapter(handler: httpx.MockTransport) -> EskizSmsProviderAdapter:
    client = httpx.AsyncClient(
        base_url=os.environ["ESKIZ_API_BASE_URL"], transport=handler, timeout=10.0
    )
    return EskizSmsProviderAdapter(client=client)


async def test_connection_failure_raises_otp_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    adapter = _adapter(httpx.MockTransport(handler))

    with pytest.raises(OtpProviderUnavailableError):
        await adapter.send_otp(phone=PhoneNumber(value="+998901234567"), code="123456")


async def test_provider_error_status_raises_otp_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"data": {"token": "tok"}})
        return httpx.Response(500, json={"message": "provider down"})

    adapter = _adapter(httpx.MockTransport(handler))

    with pytest.raises(OtpProviderUnavailableError):
        await adapter.send_otp(phone=PhoneNumber(value="+998901234567"), code="123456")


async def test_healthy_provider_sends_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"data": {"token": "tok"}})
        return httpx.Response(200, json={"id": "1"})

    adapter = _adapter(httpx.MockTransport(handler))

    await adapter.send_otp(phone=PhoneNumber(value="+998901234567"), code="123456")
