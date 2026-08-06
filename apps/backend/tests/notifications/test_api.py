"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real Postgres/identity-bridge providers swapped for in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production. Covers the 3
notifications-related operationIds (`listNotifications`/`setNotificationRead`/
`markAllNotificationsRead`) and the "own notifications only" ownership scoping. Mirrors
`apps/backend/tests/moderation/test_api.py`'s pattern exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from main import create_app
from notifications.application.notification_use_cases import NotificationUseCases
from notifications.domain import Channel, Notification
from notifications.interfaces.auth import ActingUser
from notifications.interfaces.di import get_acting_user, get_notification_use_cases
from shared_kernel import UserId

from .conftest import FakeNotificationRepository

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

TEST_USER = UserId(value=uuid4())
_TOKEN_TO_USER = {"owner-token": TEST_USER}


@pytest.fixture
def client(fake_notifications: FakeNotificationRepository) -> Iterator[TestClient]:
    def _notification_use_cases() -> NotificationUseCases:
        return NotificationUseCases(notifications=fake_notifications)

    async def acting_user_override(
        authorization: str | None = Header(default=None),
    ) -> ActingUser:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        account_id = _TOKEN_TO_USER.get(token or "")
        if account_id is None:
            raise HTTPException(status_code=401, detail="no valid session")
        return ActingUser(account_id=account_id)

    app = create_app()
    app.dependency_overrides[get_notification_use_cases] = _notification_use_cases
    app.dependency_overrides[get_acting_user] = acting_user_override

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed(fake_notifications: FakeNotificationRepository, recipient_user_id: UUID) -> Notification:
    notification = Notification.create(
        notification_id=uuid4(),
        recipient_user_id=recipient_user_id,
        event_key="UserRegistered",
        channel=Channel.EMAIL,
        template_id=uuid4(),
        template_version_id=uuid4(),
        locale="uz_latn",
        rendered_subject="Welcome",
        rendered_body="Welcome to Active Home",
        now=NOW,
    )
    fake_notifications.rows[notification.id] = notification
    return notification


# --- listNotifications --------------------------------------------------------------------------


def test_list_notifications_requires_authentication(client: TestClient) -> None:
    resp = client.get("/api/v1/me/notifications")
    assert resp.status_code == 401


def test_list_notifications_returns_only_own(
    client: TestClient, fake_notifications: FakeNotificationRepository
) -> None:
    mine = _seed(fake_notifications, TEST_USER.value)
    _seed(fake_notifications, uuid4())

    resp = client.get("/api/v1/me/notifications", headers=_auth("owner-token"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(mine.id)
    assert body["items"][0]["deliveryStatus"] == "QUEUED"


def test_list_notifications_unread_only_filter(
    client: TestClient, fake_notifications: FakeNotificationRepository
) -> None:
    unread = _seed(fake_notifications, TEST_USER.value)
    read = _seed(fake_notifications, TEST_USER.value)
    fake_notifications.rows[read.id] = read.mark_read(now=NOW)

    resp = client.get(
        "/api/v1/me/notifications",
        params={"unreadOnly": True},
        headers=_auth("owner-token"),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [item["id"] for item in items] == [str(unread.id)]


# --- setNotificationRead --------------------------------------------------------------------------


def test_set_notification_read_marks_it_read(
    client: TestClient, fake_notifications: FakeNotificationRepository
) -> None:
    mine = _seed(fake_notifications, TEST_USER.value)

    resp = client.put(
        f"/api/v1/me/notifications/{mine.id}/read",
        json={"read": True},
        headers=_auth("owner-token"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["readAt"] is not None


def test_set_notification_read_on_someone_elses_notification_returns_404(
    client: TestClient, fake_notifications: FakeNotificationRepository
) -> None:
    theirs = _seed(fake_notifications, uuid4())

    resp = client.put(
        f"/api/v1/me/notifications/{theirs.id}/read",
        json={"read": True},
        headers=_auth("owner-token"),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "RESOURCE_NOT_FOUND"


def test_set_notification_read_on_nonexistent_notification_returns_404(
    client: TestClient,
) -> None:
    resp = client.put(
        f"/api/v1/me/notifications/{uuid4()}/read",
        json={"read": True},
        headers=_auth("owner-token"),
    )
    assert resp.status_code == 404


# --- markAllNotificationsRead ----------------------------------------------------------------------


def test_mark_all_notifications_read_only_touches_own(
    client: TestClient, fake_notifications: FakeNotificationRepository
) -> None:
    mine = _seed(fake_notifications, TEST_USER.value)
    theirs = _seed(fake_notifications, uuid4())

    resp = client.post("/api/v1/me/notifications/read-all", headers=_auth("owner-token"))
    assert resp.status_code == 204

    assert fake_notifications.rows[mine.id].read_at is not None
    assert fake_notifications.rows[theirs.id].read_at is None


def test_mark_all_notifications_read_requires_authentication(
    client: TestClient,
) -> None:
    resp = client.post("/api/v1/me/notifications/read-all")
    assert resp.status_code == 401
