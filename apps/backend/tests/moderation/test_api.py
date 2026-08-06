"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real Postgres/identity-bridge providers swapped for in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production. Covers the 3
moderation-related operationIds (`listModerationQueue`/`getModerationCase`/
`applyModerationAction`) and the reviewer-only authorization gate. Mirrors
`apps/backend/tests/profiles/test_api.py`'s pattern exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from main import create_app
from moderation.application.action_service import ModerationActionService
from moderation.application.moderation_use_cases import ModerationUseCases
from moderation.domain import Subject, SubjectType
from moderation.domain.moderation_case import ModerationCase
from moderation.interfaces.auth import ActingModerator
from moderation.interfaces.di import get_acting_moderator, get_moderation_use_cases
from shared_kernel import UserId

from .conftest import (
    FakeListingModerationCommandPort,
    FakeModerationCaseRepository,
    FakeOutbox,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

TEST_MODERATOR = UserId(value=uuid4())
_MODERATOR_TOKENS = {"moderator-token"}


@pytest.fixture
def client(
    fake_cases: FakeModerationCaseRepository,
    action_service: ModerationActionService,
    fake_outbox: FakeOutbox,
) -> Iterator[TestClient]:
    def _moderation_use_cases() -> ModerationUseCases:
        return ModerationUseCases(
            cases=fake_cases, action_service=action_service, outbox=fake_outbox
        )

    async def acting_moderator_override(
        authorization: str | None = Header(default=None),
    ) -> ActingModerator:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        if token not in _MODERATOR_TOKENS:
            raise HTTPException(status_code=403, detail="not a moderator")
        return ActingModerator(account_id=TEST_MODERATOR)

    app = create_app()
    app.dependency_overrides[get_moderation_use_cases] = _moderation_use_cases
    app.dependency_overrides[get_acting_moderator] = acting_moderator_override

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_case(
    fake_cases: FakeModerationCaseRepository,
    subject_type: SubjectType = SubjectType.LISTING,
) -> ModerationCase:
    case = ModerationCase.open_from_report(
        case_id=uuid4(),
        subject=Subject(subject_type=subject_type, subject_id=uuid4()),
        reporter_user_id=uuid4(),
        reason="spam",
        now=NOW,
    )
    fake_cases.cases[case.id] = case
    return case


# --- listModerationQueue --------------------------------------------------------------------------


def test_list_moderation_queue_refuses_non_moderator(client: TestClient) -> None:
    resp = client.get("/api/v1/admin/moderation-queue", headers=_auth("nope"))
    assert resp.status_code == 403


def test_list_moderation_queue_refuses_unauthenticated(client: TestClient) -> None:
    resp = client.get("/api/v1/admin/moderation-queue")
    assert resp.status_code == 403


def test_list_moderation_queue_allows_moderator(
    client: TestClient, fake_cases: FakeModerationCaseRepository
) -> None:
    _seed_case(fake_cases)
    resp = client.get("/api/v1/admin/moderation-queue", headers=_auth("moderator-token"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == "OPEN"


def test_list_moderation_queue_filters_by_subject_type(
    client: TestClient, fake_cases: FakeModerationCaseRepository
) -> None:
    _seed_case(fake_cases, SubjectType.LISTING)
    _seed_case(fake_cases, SubjectType.USER)
    resp = client.get(
        "/api/v1/admin/moderation-queue",
        params={"subjectType": "USER"},
        headers=_auth("moderator-token"),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["subjectType"] == "USER"


# --- getModerationCase -----------------------------------------------------------------------------


def test_get_moderation_case(client: TestClient, fake_cases: FakeModerationCaseRepository) -> None:
    case = _seed_case(fake_cases)
    resp = client.get(f"/api/v1/admin/moderation-queue/{case.id}", headers=_auth("moderator-token"))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(case.id)


def test_get_nonexistent_moderation_case_returns_404(client: TestClient) -> None:
    resp = client.get(f"/api/v1/admin/moderation-queue/{uuid4()}", headers=_auth("moderator-token"))
    assert resp.status_code == 404
    assert resp.json()["code"] == "RESOURCE_NOT_FOUND"


def test_get_moderation_case_refuses_non_moderator(
    client: TestClient, fake_cases: FakeModerationCaseRepository
) -> None:
    case = _seed_case(fake_cases)
    resp = client.get(f"/api/v1/admin/moderation-queue/{case.id}")
    assert resp.status_code == 403


# --- applyModerationAction -------------------------------------------------------------------------


def test_apply_moderation_action_resolves_case_and_dispatches_command(
    client: TestClient,
    fake_cases: FakeModerationCaseRepository,
    fake_listings: FakeListingModerationCommandPort,
) -> None:
    case = _seed_case(fake_cases, SubjectType.LISTING)
    resp = client.post(
        f"/api/v1/admin/moderation-queue/{case.id}/action",
        json={"action": "HIDE", "note": "policy violation"},
        headers=_auth("moderator-token"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "RESOLVED"
    assert body["resolutionAction"] == "HIDE"
    assert len(fake_listings.calls) == 1
    assert fake_listings.calls[0][0] == "hide_listing"


def test_apply_moderation_action_refuses_invalid_pairing(
    client: TestClient, fake_cases: FakeModerationCaseRepository
) -> None:
    case = _seed_case(fake_cases, SubjectType.LISTING)
    resp = client.post(
        f"/api/v1/admin/moderation-queue/{case.id}/action",
        json={"action": "SUSPEND_ACCOUNT"},
        headers=_auth("moderator-token"),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_FAILED"


def test_apply_moderation_action_refuses_non_moderator(
    client: TestClient, fake_cases: FakeModerationCaseRepository
) -> None:
    case = _seed_case(fake_cases)
    resp = client.post(f"/api/v1/admin/moderation-queue/{case.id}/action", json={"action": "HIDE"})
    assert resp.status_code == 403


def test_apply_moderation_action_on_resolved_case_returns_conflict(
    client: TestClient, fake_cases: FakeModerationCaseRepository
) -> None:
    case = _seed_case(fake_cases)
    first = client.post(
        f"/api/v1/admin/moderation-queue/{case.id}/action",
        json={"action": "DISMISS"},
        headers=_auth("moderator-token"),
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/admin/moderation-queue/{case.id}/action",
        json={"action": "DISMISS"},
        headers=_auth("moderator-token"),
    )
    assert second.status_code == 409
    assert second.json()["code"] == "ILLEGAL_STATE_TRANSITION"
