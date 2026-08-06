"""notifications/application -- `NotificationDispatchUseCases` (Task P-13): the module's central
event-driven flow -- "handle-domain-event -> resolve -> check-preferences -> dispatch"
(DDD Sec 5.10 `NotificationDispatchService`). Split into two methods on purpose (Playbook Sec 6:
"a transaction is never held open across a provider port call"):

`queue_for_event` resolves the recipient's already-fetched contact/preference snapshot, the
PUBLISHED template(s) for the event, applies `PreferencePolicy` (FR-NOTIF-004), and persists one
`QUEUED` `Notification` row per (channel, template) pair that passes -- called INSIDE the
idempotent-consumer's own DB transaction (`infrastructure/event_projection.py`), so redelivery of
the same event never creates a second row (the `ProcessedEvent` ledger guard wraps this whole
method's caller).

`dispatch_queued` makes the actual channel-provider call and persists the outcome -- called
OUTSIDE any open transaction, in the worker's own post-commit step. A preference-suppressed
(channel, template) pair never reaches either method at all: it is dropped before a `Notification`
row would ever be created (Physical DB's own closed `delivery_status` CHECK has no `SUPPRESSED`
member -- confirmed against `Physical-Database-Design-and-ERD` Sec 2.10).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from notifications.application.exceptions import RecipientMissingContactDetailError
from notifications.application.ports import (
    EmailProviderPort,
    NotificationRepository,
    NotificationTemplateSnapshot,
    RecipientSnapshot,
    SmsProviderPort,
    TemplateReaderPort,
    WebPushProviderPort,
)
from notifications.domain import Channel, Notification, UnsupportedChannelError
from shared_kernel import LocalizedText

_logger = logging.getLogger(__name__)

_DEFAULT_LOCALE = "uz_latn"
"""No approved document specifies where a recipient's preferred locale for ASYNCHRONOUS dispatch
is persisted (`identity.user_account` has no locale column; `Accept-Language` is transport-only/
per-request, unusable for a background worker with no active HTTP request -- confirmed against
DDD Sec 5.1's own UserAccount VO list and the Physical Database Design's full column list).
Resolved (with explicit sign-off) as: every dispatch resolves to the canonical `uz_latn` (DEC-19)
until a future task adds a persisted per-recipient locale preference -- the resolution/rendering
machinery below already supports all four locales structurally, exercised by synthetic recipient
locales in tests."""


def _resolve_text(text: LocalizedText, locale: str) -> str:
    value = getattr(text, locale, None)
    if value:
        return str(value)
    # `uz_latn` is REQUIRED on every PUBLISHED template (configuration's own gate,
    # `_check_translations`) -- guaranteed present; this is a defensive fallback only.
    if text.uz_latn:
        return text.uz_latn
    for fallback_locale in ("uz_cyrl", "ru", "en"):
        value = getattr(text, fallback_locale, None)
        if value:
            return str(value)
    raise UnsupportedChannelError(
        locale
    )  # pragma: no cover -- unreachable for a published template


def _preference_allows(recipient: RecipientSnapshot, channel: Channel) -> bool:
    if channel is Channel.EMAIL:
        return recipient.email_enabled and recipient.email is not None
    if channel is Channel.SMS:
        return recipient.sms_enabled and recipient.phone is not None
    if channel is Channel.WEB_PUSH:
        return recipient.web_push_enabled and recipient.web_push_subscription is not None
    raise UnsupportedChannelError(channel.value)  # pragma: no cover -- Channel is a closed enum


@dataclass(frozen=True)
class QueuedDispatch:
    notification: Notification
    recipient: RecipientSnapshot


class NotificationDispatchUseCases:
    def __init__(
        self,
        *,
        notifications: NotificationRepository,
        templates: TemplateReaderPort,
        email: EmailProviderPort,
        sms: SmsProviderPort,
        web_push: WebPushProviderPort,
    ) -> None:
        self._notifications = notifications
        self._templates = templates
        self._email = email
        self._sms = sms
        self._web_push = web_push

    async def queue_for_event(
        self, *, event_key: str, recipient: RecipientSnapshot | None, now: datetime
    ) -> list[QueuedDispatch]:
        if recipient is None:
            return []
        templates = await self._templates.list_templates_for_event(event_key)
        queued: list[QueuedDispatch] = []
        for template in templates:
            channel = _channel_of(template)
            if not _preference_allows(recipient, channel):
                continue
            notification = Notification.create(
                notification_id=uuid4(),
                recipient_user_id=recipient.user_id,
                event_key=event_key,
                channel=channel,
                template_id=template.template_id,
                template_version_id=template.template_version_id,
                locale=_DEFAULT_LOCALE,
                rendered_subject=(
                    _resolve_text(template.subject, _DEFAULT_LOCALE) if template.subject else None
                ),
                rendered_body=_resolve_text(template.body, _DEFAULT_LOCALE),
                now=now,
            )
            await self._notifications.add(notification)
            queued.append(QueuedDispatch(notification=notification, recipient=recipient))
        return queued

    async def dispatch_queued(self, dispatch: QueuedDispatch, *, now: datetime) -> Notification:
        """Never called from inside a DB transaction (Playbook Sec 6) -- the caller (the worker)
        commits `queue_for_event`'s own transaction first, then calls this per queued item, then
        persists the outcome in its own short follow-up transaction via `self._notifications.
        save`. Fails closed: ANY exception from the provider call (missing credentials, provider
        error, timeout) marks the notification `FAILED` -- never `SENT`, never a silent fallback
        to a different channel (each call is scoped to exactly one channel). Logged with ONLY
        safe identifiers (notification id, channel, event_key) -- NEVER the recipient's email/
        phone/push endpoint or the rendered message body (Security Sec 12 PII rule)."""
        notification = dispatch.notification
        try:
            provider_ref = await self._send(notification, dispatch.recipient)
        except Exception:
            _logger.warning(
                "notification dispatch failed, marking FAILED",
                extra={
                    "notification_id": str(notification.id),
                    "channel": notification.channel.value,
                    "event_key": notification.event_key,
                },
            )
            return await self._notifications.save(notification.mark_failed(now=now))
        return await self._notifications.save(
            notification.mark_sent(provider_message_ref=provider_ref, now=now)
        )

    async def _send(self, notification: Notification, recipient: RecipientSnapshot) -> str:
        if notification.channel is Channel.EMAIL:
            if recipient.email is None:
                raise RecipientMissingContactDetailError(recipient.user_id, Channel.EMAIL.value)
            return await self._email.send_email(
                to_email=recipient.email,
                subject=notification.rendered_subject,
                body=notification.rendered_body,
            )
        if notification.channel is Channel.SMS:
            if recipient.phone is None:
                raise RecipientMissingContactDetailError(recipient.user_id, Channel.SMS.value)
            return await self._sms.send_sms(phone=recipient.phone, body=notification.rendered_body)
        if notification.channel is Channel.WEB_PUSH:
            if recipient.web_push_subscription is None:
                raise RecipientMissingContactDetailError(recipient.user_id, Channel.WEB_PUSH.value)
            return await self._web_push.send_push(
                subscription=recipient.web_push_subscription,
                body=notification.rendered_body,
            )
        raise UnsupportedChannelError(notification.channel.value)  # pragma: no cover


def _channel_of(template: NotificationTemplateSnapshot) -> Channel:
    try:
        return Channel(template.channel)
    except ValueError as exc:
        raise UnsupportedChannelError(template.channel) from exc
