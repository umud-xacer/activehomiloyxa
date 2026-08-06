"""Eskiz SMS provider adapter (DEC-18, Baseline: "SMS, Web Push; SMS OTP via Eskiz"). Implements
`notifications.application.ports.SmsProviderPort`. Eskiz's own request/response shapes are
confined entirely to this file. A SEPARATE adapter from `identity.infrastructure.providers.eskiz.
EskizSmsProviderAdapter` (that one sends OTP codes synchronously on the request path and is out
of this module's reach -- `cross-module-notifications` forbids importing `identity`; OTP itself
has no domain event in the frozen catalogue for this module to react to, see README "Known
gaps") -- reuses the SAME `ESKIZ_API_BASE_URL`/`ESKIZ_EMAIL`/`ESKIZ_PASSWORD`/
`ESKIZ_SENDER_NICKNAME` environment variables (DEC-18: one fixed provider, two independent
adapters, mirroring `providers/email.py`'s own precedent note)."""

from __future__ import annotations

import time

import httpx

from backbone.persistence.env import required_env


class EskizSmsProviderAdapter:
    _TOKEN_TTL_SECONDS = 25 * 24 * 3600
    """Eskiz issues bearer tokens valid ~30 days; refreshed a few days early."""

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=required_env("ESKIZ_API_BASE_URL"), timeout=10.0
        )
        self._email = required_env("ESKIZ_EMAIL")
        self._password = required_env("ESKIZ_PASSWORD")
        self._sender_nickname = required_env("ESKIZ_SENDER_NICKNAME")
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def send_sms(self, *, phone: str, body: str) -> str:
        token = await self._get_token()
        response = await self._client.post(
            "/message/sms/send",
            data={
                "mobile_phone": phone.lstrip("+"),
                "message": body,
                "from": self._sender_nickname,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        data = response.json()
        message_id = data.get("id") or data.get("data", {}).get("id")
        return str(message_id) if message_id is not None else str(data)

    async def _get_token(self) -> str:
        if self._token is not None and time.monotonic() < self._token_expires_at:
            return self._token
        response = await self._client.post(
            "/auth/login", data={"email": self._email, "password": self._password}
        )
        response.raise_for_status()
        token: str = response.json()["data"]["token"]
        self._token = token
        self._token_expires_at = time.monotonic() + self._TOKEN_TTL_SECONDS
        return token
