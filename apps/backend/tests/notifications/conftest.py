"""Shared fixtures for `notifications`' fast (no-DB) unit + API tests: in-memory fakes for every
port `application/ports.py` declares. Mirrors `apps/backend/tests/moderation/conftest.py`'s
pattern exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from notifications.application.ports import (
    NotificationTemplateSnapshot,
    RecipientSnapshot,
    WebPushSubscriptionSnapshot,
)
from notifications.domain import Notification


@dataclass
class FakeNotificationRepository:
    rows: dict[UUID, Notification] = field(default_factory=dict)

    async def add(self, notification: Notification) -> None:
        self.rows[notification.id] = notification

    async def save(self, notification: Notification) -> Notification:
        self.rows[notification.id] = notification
        return notification

    async def get_by_id(self, notification_id: UUID) -> Notification | None:
        return self.rows.get(notification_id)

    async def list_for_recipient(
        self,
        recipient_user_id: UUID,
        *,
        unread_only: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Notification], str | None]:
        items = [n for n in self.rows.values() if n.recipient_user_id == recipient_user_id]
        if unread_only:
            items = [n for n in items if n.read_at is None]
        items.sort(key=lambda n: n.created_at, reverse=True)
        return items[:limit], None


@dataclass
class FakeTemplateReaderPort:
    templates: dict[str, tuple[NotificationTemplateSnapshot, ...]] = field(default_factory=dict)

    def seed(self, event_key: str, *snapshots: NotificationTemplateSnapshot) -> None:
        self.templates[event_key] = snapshots

    async def list_templates_for_event(
        self, event_key: str
    ) -> tuple[NotificationTemplateSnapshot, ...]:
        return self.templates.get(event_key, ())


@dataclass
class FakeRecipientDirectoryPort:
    by_user: dict[UUID, RecipientSnapshot] = field(default_factory=dict)
    by_profile: dict[UUID, RecipientSnapshot] = field(default_factory=dict)
    by_listing: dict[UUID, RecipientSnapshot] = field(default_factory=dict)

    async def resolve_recipient(self, user_id: UUID) -> RecipientSnapshot | None:
        return self.by_user.get(user_id)

    async def resolve_recipient_for_profile(self, profile_id: UUID) -> RecipientSnapshot | None:
        return self.by_profile.get(profile_id)

    async def resolve_recipient_for_listing(self, listing_id: UUID) -> RecipientSnapshot | None:
        return self.by_listing.get(listing_id)


@dataclass
class FakeOrderRecipientProjectionRepository:
    rows: dict[UUID, UUID] = field(default_factory=dict)

    async def upsert(self, *, order_id: UUID, purchaser_profile_id: UUID) -> None:
        self.rows[order_id] = purchaser_profile_id

    async def get_purchaser_profile_id(self, order_id: UUID) -> UUID | None:
        return self.rows.get(order_id)


class FakeEmailProviderPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str | None, str]] = []

    async def send_email(self, *, to_email: str, subject: str | None, body: str) -> str:
        if self.fail:
            raise RuntimeError("email provider unavailable")
        self.calls.append((to_email, subject, body))
        return f"email-msg-{len(self.calls)}"


class FakeSmsProviderPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def send_sms(self, *, phone: str, body: str) -> str:
        if self.fail:
            raise RuntimeError("sms provider unavailable")
        self.calls.append((phone, body))
        return f"sms-msg-{len(self.calls)}"


class FakeWebPushProviderPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[WebPushSubscriptionSnapshot, str]] = []

    async def send_push(self, *, subscription: WebPushSubscriptionSnapshot, body: str) -> str:
        if self.fail:
            raise RuntimeError("web-push provider unavailable")
        self.calls.append((subscription, body))
        return subscription.endpoint


@pytest.fixture
def fake_notifications() -> FakeNotificationRepository:
    return FakeNotificationRepository()


@pytest.fixture
def fake_templates() -> FakeTemplateReaderPort:
    return FakeTemplateReaderPort()


@pytest.fixture
def fake_recipients() -> FakeRecipientDirectoryPort:
    return FakeRecipientDirectoryPort()


@pytest.fixture
def fake_order_projection() -> FakeOrderRecipientProjectionRepository:
    return FakeOrderRecipientProjectionRepository()


@pytest.fixture
def fake_email() -> FakeEmailProviderPort:
    return FakeEmailProviderPort()


@pytest.fixture
def fake_sms() -> FakeSmsProviderPort:
    return FakeSmsProviderPort()


@pytest.fixture
def fake_web_push() -> FakeWebPushProviderPort:
    return FakeWebPushProviderPort()
