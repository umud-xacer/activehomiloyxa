"""SMTP-based `EmailProviderPort` adapter (DEC-18). Reuses the SAME `SMTP_HOST`/`SMTP_PORT`/
`SMTP_USER`/`SMTP_PASSWORD` environment variables identity's own `SmtpEmailProviderAdapter`
already declared under "Notifications channels (Notifications module, template-based delivery)"
in `deployment/env/.env.*.example` -- that module's own docstring names this task as the
"future Notifications-module task [that] may prefer to own all outbound email via an event-driven
flow" it anticipated. A SEPARATE adapter class, not a shared one: notifications may not statically
import `identity` (`cross-module-notifications`), so each module owns its own SMTP integration
against the same relay config, exactly the same "two independent adapters, one fixed provider"
shape DEC-18 already establishes for Eskiz (identity's own OTP adapter vs. this module's own).
`smtplib` is synchronous; each send is offloaded to a worker thread so it never blocks the event
loop (Playbook Sec 6)."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from backbone.persistence.env import required_env

_FROM_ADDRESS = "Active Home <noreply@activehome.uz>"
"""Not a secret -- a fixed sender identity, not environment-specific config."""


class SmtpEmailProviderAdapter:
    def __init__(self) -> None:
        self._host = required_env("SMTP_HOST")
        self._port = int(required_env("SMTP_PORT"))
        self._username = required_env("SMTP_USER")
        self._password = required_env("SMTP_PASSWORD")

    async def send_email(self, *, to_email: str, subject: str | None, body: str) -> str:
        message = EmailMessage()
        message["Subject"] = subject or "Active Home notification"
        message["From"] = _FROM_ADDRESS
        message["To"] = to_email
        message_id = make_msgid()
        message["Message-ID"] = message_id
        message.set_content(body)
        await asyncio.to_thread(self._send, message)
        return message_id

    def _send(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=10) as client:
            client.starttls()
            client.login(self._username, self._password)
            client.send_message(message)
