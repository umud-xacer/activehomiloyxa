"""`notifications.application.NotificationDispatchUseCases` (Task P-13) -- exercised against the
in-memory fakes in `conftest.py`. Covers template resolution by (event_key, channel), all-four-
locale rendering, preference suppression, the QUEUED->SENT/FAILED transaction-hygiene split
(`queue_for_event` vs. `dispatch_queued`), and the fail-closed guarantee.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from notifications.application.dispatch_use_cases import (
    NotificationDispatchUseCases,
    QueuedDispatch,
)
from notifications.application.exceptions import RecipientMissingContactDetailError
from notifications.application.ports import (
    NotificationTemplateSnapshot,
    RecipientSnapshot,
    WebPushSubscriptionSnapshot,
)
from notifications.domain import Channel, DeliveryStatus, Notification, UnsupportedChannelError
from shared_kernel import LocalizedText

from .conftest import (
    FakeEmailProviderPort,
    FakeNotificationRepository,
    FakeSmsProviderPort,
    FakeTemplateReaderPort,
    FakeWebPushProviderPort,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _use_cases(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> NotificationDispatchUseCases:
    return NotificationDispatchUseCases(
        notifications=fake_notifications,
        templates=fake_templates,
        email=fake_email,
        sms=fake_sms,
        web_push=fake_web_push,
    )


def _email_template(event_key: str = "UserRegistered") -> NotificationTemplateSnapshot:
    return NotificationTemplateSnapshot(
        template_id=uuid4(),
        template_version_id=uuid4(),
        event_key=event_key,
        channel="EMAIL",
        subject=LocalizedText(
            uz_latn="Xush kelibsiz",
            uz_cyrl="Хуш келибсиз",
            ru="Добро пожаловать",
            en="Welcome",
        ),
        body=LocalizedText(
            uz_latn="Platformaga xush kelibsiz",
            uz_cyrl="Платформага хуш келибсиз",
            ru="Добро пожаловать на платформу",
            en="Welcome to the platform",
        ),
    )


def _recipient(**overrides: object) -> RecipientSnapshot:
    defaults: dict[str, object] = {
        "user_id": uuid4(),
        "email": "user@example.com",
        "phone": "+998901234567",
        "web_push_subscription": None,
        "email_enabled": True,
        "web_push_enabled": True,
        "sms_enabled": True,
    }
    defaults.update(overrides)
    return RecipientSnapshot(**defaults)  # type: ignore[arg-type]


# --- template resolution + localization -----------------------------------------------------


@pytest.mark.asyncio
async def test_queue_for_event_resolves_template_by_event_key_and_channel(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    fake_templates.seed("UserRegistered", _email_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    recipient = _recipient()

    queued = await use_cases.queue_for_event(
        event_key="UserRegistered", recipient=recipient, now=NOW
    )

    assert len(queued) == 1
    notification = queued[0].notification
    assert notification.channel is Channel.EMAIL
    assert notification.delivery_status is DeliveryStatus.QUEUED
    assert notification.locale == "uz_latn"
    assert notification.rendered_body == "Platformaga xush kelibsiz"
    assert notification.rendered_subject == "Xush kelibsiz"


@pytest.mark.parametrize(
    ("locale", "expected_body"),
    [
        ("uz_latn", "Platformaga xush kelibsiz"),
        ("uz_cyrl", "Платформага хуш келибсиз"),
        ("ru", "Добро пожаловать на платформу"),
        ("en", "Welcome to the platform"),
    ],
)
@pytest.mark.asyncio
async def test_all_four_locales_resolve_correctly(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
    locale: str,
    expected_body: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import notifications.application.dispatch_use_cases as dispatch_module

    monkeypatch.setattr(dispatch_module, "_DEFAULT_LOCALE", locale)
    fake_templates.seed("UserRegistered", _email_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)

    queued = await use_cases.queue_for_event(
        event_key="UserRegistered", recipient=_recipient(), now=NOW
    )

    assert queued[0].notification.rendered_body == expected_body
    assert queued[0].notification.locale == locale


@pytest.mark.asyncio
async def test_no_template_for_event_means_no_notification(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    queued = await use_cases.queue_for_event(
        event_key="ListingPublished", recipient=_recipient(), now=NOW
    )
    assert queued == []
    assert fake_notifications.rows == {}


@pytest.mark.asyncio
async def test_no_recipient_means_no_notification(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    fake_templates.seed("UserRegistered", _email_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    queued = await use_cases.queue_for_event(event_key="UserRegistered", recipient=None, now=NOW)
    assert queued == []


# --- preference suppression -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_channel_preference_suppresses_delivery_no_row_created(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    fake_templates.seed("UserRegistered", _email_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    recipient = _recipient(email_enabled=False)

    queued = await use_cases.queue_for_event(
        event_key="UserRegistered", recipient=recipient, now=NOW
    )

    assert queued == []
    assert fake_notifications.rows == {}, "a suppressed notification must never become a row at all"


@pytest.mark.asyncio
async def test_missing_contact_info_suppresses_delivery_even_if_preference_enabled(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    fake_templates.seed("UserRegistered", _email_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    recipient = _recipient(email=None, email_enabled=True)

    queued = await use_cases.queue_for_event(
        event_key="UserRegistered", recipient=recipient, now=NOW
    )
    assert queued == []


# --- dispatch: fail-closed + transaction hygiene -----------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_queued_success_marks_sent_with_provider_ref(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    fake_templates.seed("UserRegistered", _email_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    queued = await use_cases.queue_for_event(
        event_key="UserRegistered", recipient=_recipient(), now=NOW
    )

    result = await use_cases.dispatch_queued(queued[0], now=NOW)

    assert result.delivery_status is DeliveryStatus.SENT
    assert result.provider_message_ref == "email-msg-1"
    assert fake_email.calls == [("user@example.com", "Xush kelibsiz", "Platformaga xush kelibsiz")]


@pytest.mark.asyncio
async def test_dispatch_queued_provider_failure_fails_closed_never_marks_sent(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    failing_email = FakeEmailProviderPort(fail=True)
    fake_templates.seed("UserRegistered", _email_template())
    use_cases = _use_cases(
        fake_notifications, fake_templates, failing_email, fake_sms, fake_web_push
    )
    queued = await use_cases.queue_for_event(
        event_key="UserRegistered", recipient=_recipient(), now=NOW
    )

    result = await use_cases.dispatch_queued(queued[0], now=NOW)

    assert result.delivery_status is DeliveryStatus.FAILED
    assert result.provider_message_ref is None


@pytest.mark.asyncio
async def test_queue_for_event_never_calls_any_provider_port(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    """Transaction-hygiene guarantee (Playbook Sec 6): `queue_for_event` -- the DB-writing half,
    called from inside the idempotent-consumer's own transaction -- must never itself make a
    provider call; only the separate `dispatch_queued` (called after that transaction commits)
    ever touches a channel port."""
    fake_templates.seed("UserRegistered", _email_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)

    await use_cases.queue_for_event(event_key="UserRegistered", recipient=_recipient(), now=NOW)

    assert fake_email.calls == []
    assert fake_sms.calls == []
    assert fake_web_push.calls == []


# --- dispatch-time contact-detail race (RecipientMissingContactDetailError) --------------------


def _queued_dispatch(*, channel: Channel, recipient: RecipientSnapshot) -> QueuedDispatch:
    """A `QueuedDispatch` built directly (bypassing `queue_for_event`'s own `_preference_allows`
    check), simulating `RecipientMissingContactDetailError`'s documented scenario: the contact
    detail was present when this row was queued, but the recipient's snapshot changed by the
    time `dispatch_queued` actually runs (e.g. the user cleared their email in between)."""
    return QueuedDispatch(
        notification=Notification.create(
            notification_id=uuid4(),
            recipient_user_id=recipient.user_id,
            event_key="UserRegistered",
            channel=channel,
            template_id=uuid4(),
            template_version_id=uuid4(),
            locale="uz_latn",
            rendered_subject=None,
            rendered_body="body",
            now=NOW,
        ),
        recipient=recipient,
    )


@pytest.mark.asyncio
async def test_email_dispatch_fails_closed_when_contact_detail_missing_at_dispatch_time(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    dispatch = _queued_dispatch(channel=Channel.EMAIL, recipient=_recipient(email=None))

    result = await use_cases.dispatch_queued(dispatch, now=NOW)

    assert result.delivery_status is DeliveryStatus.FAILED
    assert result.provider_message_ref is None
    assert fake_email.calls == [], "must fail before ever reaching the provider port"


@pytest.mark.asyncio
async def test_sms_dispatch_fails_closed_when_contact_detail_missing_at_dispatch_time(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    dispatch = _queued_dispatch(channel=Channel.SMS, recipient=_recipient(phone=None))

    result = await use_cases.dispatch_queued(dispatch, now=NOW)

    assert result.delivery_status is DeliveryStatus.FAILED
    assert result.provider_message_ref is None
    assert fake_sms.calls == [], "must fail before ever reaching the provider port"


@pytest.mark.asyncio
async def test_web_push_dispatch_fails_closed_when_contact_detail_missing_at_dispatch_time(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    dispatch = _queued_dispatch(
        channel=Channel.WEB_PUSH, recipient=_recipient(web_push_subscription=None)
    )

    result = await use_cases.dispatch_queued(dispatch, now=NOW)

    assert result.delivery_status is DeliveryStatus.FAILED
    assert result.provider_message_ref is None
    assert fake_web_push.calls == [], "must fail before ever reaching the provider port"


def test_recipient_missing_contact_detail_error_carries_user_id_and_channel() -> None:
    """Direct unit coverage of the exception's own `__init__` (application/exceptions.py) --
    the three dispatch-time tests above exercise it only indirectly through
    `dispatch_queued`'s broad `except Exception:` catch, which never surfaces the exception's
    attributes for assertion."""
    user_id = uuid4()

    error = RecipientMissingContactDetailError(user_id, "EMAIL")

    assert error.user_id == user_id
    assert error.channel == "EMAIL"
    assert str(user_id) in str(error)
    assert "EMAIL" in str(error)


# --- SMS + web-push channels -------------------------------------------------------------------


def _sms_template(event_key: str = "AccountSuspended") -> NotificationTemplateSnapshot:
    return NotificationTemplateSnapshot(
        template_id=uuid4(),
        template_version_id=uuid4(),
        event_key=event_key,
        channel="SMS",
        subject=None,
        body=LocalizedText(uz_latn="Hisobingiz vaqtincha to'xtatildi"),
    )


def _web_push_template(event_key: str = "MessageSent") -> NotificationTemplateSnapshot:
    return NotificationTemplateSnapshot(
        template_id=uuid4(),
        template_version_id=uuid4(),
        event_key=event_key,
        channel="WEB_PUSH",
        subject=None,
        body=LocalizedText(uz_latn="Sizga yangi xabar keldi"),
    )


@pytest.mark.asyncio
async def test_sms_channel_end_to_end(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    fake_templates.seed("AccountSuspended", _sms_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    queued = await use_cases.queue_for_event(
        event_key="AccountSuspended", recipient=_recipient(), now=NOW
    )
    assert queued[0].notification.channel is Channel.SMS

    result = await use_cases.dispatch_queued(queued[0], now=NOW)

    assert result.delivery_status is DeliveryStatus.SENT
    assert fake_sms.calls == [("+998901234567", "Hisobingiz vaqtincha to'xtatildi")]


@pytest.mark.asyncio
async def test_sms_channel_suppressed_without_a_phone_number(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    fake_templates.seed("AccountSuspended", _sms_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    queued = await use_cases.queue_for_event(
        event_key="AccountSuspended", recipient=_recipient(phone=None), now=NOW
    )
    assert queued == []


@pytest.mark.asyncio
async def test_web_push_channel_end_to_end(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    subscription = WebPushSubscriptionSnapshot(
        endpoint="https://push.example.test/xyz", p256dh="p256dh-key", auth="auth-key"
    )
    fake_templates.seed("MessageSent", _web_push_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    queued = await use_cases.queue_for_event(
        event_key="MessageSent",
        recipient=_recipient(web_push_subscription=subscription),
        now=NOW,
    )
    assert queued[0].notification.channel is Channel.WEB_PUSH

    result = await use_cases.dispatch_queued(queued[0], now=NOW)

    assert result.delivery_status is DeliveryStatus.SENT
    assert result.provider_message_ref == subscription.endpoint
    assert fake_web_push.calls == [(subscription, "Sizga yangi xabar keldi")]


@pytest.mark.asyncio
async def test_web_push_channel_suppressed_without_a_subscription(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    fake_templates.seed("MessageSent", _web_push_template())
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)
    queued = await use_cases.queue_for_event(
        event_key="MessageSent",
        recipient=_recipient(web_push_subscription=None),
        now=NOW,
    )
    assert queued == []


# --- defence in depth: unsupported channel -----------------------------------------------------


@pytest.mark.asyncio
async def test_template_with_an_unsupported_channel_string_raises(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
) -> None:
    """Defence in depth (`domain.exceptions.UnsupportedChannelError`'s own docstring):
    `configuration`'s own whitelist gate already rejects this at authoring time, so this can only
    fire if a snapshot somehow diverges from that whitelist."""
    bad_template = NotificationTemplateSnapshot(
        template_id=uuid4(),
        template_version_id=uuid4(),
        event_key="UserRegistered",
        channel="TELEGRAM",
        subject=None,
        body=LocalizedText(uz_latn="x"),
    )
    fake_templates.seed("UserRegistered", bad_template)
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)

    with pytest.raises(UnsupportedChannelError):
        await use_cases.queue_for_event(event_key="UserRegistered", recipient=_recipient(), now=NOW)


# --- locale fallback ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_locale_falls_back_to_uz_latn_when_the_requested_locale_has_no_translation(
    fake_notifications: FakeNotificationRepository,
    fake_templates: FakeTemplateReaderPort,
    fake_email: FakeEmailProviderPort,
    fake_sms: FakeSmsProviderPort,
    fake_web_push: FakeWebPushProviderPort,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import notifications.application.dispatch_use_cases as dispatch_module

    monkeypatch.setattr(dispatch_module, "_DEFAULT_LOCALE", "en")
    template = NotificationTemplateSnapshot(
        template_id=uuid4(),
        template_version_id=uuid4(),
        event_key="UserRegistered",
        channel="EMAIL",
        subject=None,
        body=LocalizedText(uz_latn="Faqat uz_latn tarjimasi mavjud"),  # no "en" translation
    )
    fake_templates.seed("UserRegistered", template)
    use_cases = _use_cases(fake_notifications, fake_templates, fake_email, fake_sms, fake_web_push)

    queued = await use_cases.queue_for_event(
        event_key="UserRegistered", recipient=_recipient(), now=NOW
    )

    assert queued[0].notification.rendered_body == "Faqat uz_latn tarjimasi mavjud"
