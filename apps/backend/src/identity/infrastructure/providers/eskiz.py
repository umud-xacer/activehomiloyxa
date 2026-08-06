"""Eskiz SMS provider adapter (DEC-18, Baseline Sec 4-A: "phone (SMS OTP via Eskiz)"). Implements
`identity.application.ports.OtpSmsProviderPort`. Eskiz's own request/response shapes are
confined entirely to this file -- `send_otp`'s plain `phone`/`code` strings are the only thing
that crosses the port boundary, and the code is never written to a log (only sent in the SMS
body, which is the point). `ESKIZ_API_BASE_URL`/`ESKIZ_EMAIL`/`ESKIZ_PASSWORD` are already
declared in `deployment/env/.env.*.example`; `ESKIZ_SENDER_NICKNAME` (Eskiz's required "from"
identifier) is added there by this task since no prior module needed it.
"""

from __future__ import annotations

import time

import httpx

from backbone.persistence.env import required_env
from identity.application.exceptions import OtpProviderUnavailableError
from identity.domain import PhoneNumber

_TOKEN_TTL_SECONDS = 25 * 24 * 3600
"""Eskiz issues bearer tokens valid ~30 days; refreshed a few days early."""


class EskizSmsProviderAdapter:
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=required_env("ESKIZ_API_BASE_URL"), timeout=10.0
        )
        self._email = required_env("ESKIZ_EMAIL")
        self._password = required_env("ESKIZ_PASSWORD")
        self._sender_nickname = required_env("ESKIZ_SENDER_NICKNAME")
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def send_otp(self, *, phone: PhoneNumber, code: str) -> None:
        token = await self._get_token()
        try:
            response = await self._client.post(
                "/message/sms/send",
                data={
                    "mobile_phone": phone.value.lstrip("+"),
                    "message": f"Active Home tasdiqlash kodi: {code}",
                    "from": self._sender_nickname,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # UNF-032: httpx's own exception never crosses the port boundary -- `interfaces/`
            # must not know this adapter happens to use httpx (DEC-18 provider confinement), and
            # letting it reach the generic catch-all reported a degraded SMS provider as this
            # app's own 500 "Internal server error", telling every caller the wrong thing.
            raise OtpProviderUnavailableError("Eskiz SMS send failed") from exc

    async def _get_token(self) -> str:
        if self._token is not None and time.monotonic() < self._token_expires_at:
            return self._token
        try:
            response = await self._client.post(
                "/auth/login", data={"email": self._email, "password": self._password}
            )
            response.raise_for_status()
            token: str = response.json()["data"]["token"]
        except httpx.HTTPError as exc:
            raise OtpProviderUnavailableError("Eskiz auth failed") from exc
        self._token = token
        self._token_expires_at = time.monotonic() + _TOKEN_TTL_SECONDS
        return token
