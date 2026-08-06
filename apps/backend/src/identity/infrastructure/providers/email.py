"""SMTP-based `EmailProviderPort` adapter. The Baseline (DEC-18, Sec 4-A) names Eskiz (SMS) and
Yandex Maps (geo) as the fixed v1 external providers; no email-sending vendor is named anywhere
in the approved documents. Rather than inventing an undocumented vendor integration, this
adapter targets a standard SMTP relay via the `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`
environment variables already declared in `deployment/env/.env.*.example` (under "Notifications
channels (Notifications module, template-based delivery)") -- this task reuses that same relay
config for identity's own transactional, auth-critical email (registration confirmation, account
recovery) rather than adding a second SMTP credential set; see identity/README.md "Known gaps"
for the note that a future Notifications-module task may prefer to own all outbound email via an
event-driven flow instead of each module sending directly. `smtplib` is synchronous; each send is
offloaded to a worker thread so it never blocks the event loop (Playbook Sec 6: "I/O ... MUST be
non-blocking")."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from backbone.persistence.env import required_env
from identity.domain import EmailAddress

_FROM_ADDRESS = "Active Home <noreply@activehome.uz>"
"""Not a secret -- a fixed sender identity, not environment-specific config."""


class SmtpEmailProviderAdapter:
    def __init__(self) -> None:
        self._host = required_env("SMTP_HOST")
        self._port = int(required_env("SMTP_PORT"))
        self._username = required_env("SMTP_USER")
        self._password = required_env("SMTP_PASSWORD")

    async def send_email_confirmation(self, *, email: EmailAddress, token: str) -> None:
        message = EmailMessage()
        message["Subject"] = "Confirm your Active Home account"
        message["From"] = _FROM_ADDRESS
        message["To"] = email.value
        message.set_content(f"Confirmation token: {token}")
        await asyncio.to_thread(self._send, message)

    async def send_recovery_notice(self, *, email: EmailAddress) -> None:
        message = EmailMessage()
        message["Subject"] = "Active Home account recovery"
        message["From"] = _FROM_ADDRESS
        message["To"] = email.value
        message.set_content("If you requested account recovery, contact support to complete it.")
        await asyncio.to_thread(self._send, message)

    def _send(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=10) as client:
            client.starttls()
            client.login(self._username, self._password)
            client.send_message(message)
