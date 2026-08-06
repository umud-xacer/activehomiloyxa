"""API-shape tests against the real FastAPI app (`main.create_app`), with the composition root's
real Postgres/identity providers swapped for in-memory fakes (`conftest.py`) via
`app.dependency_overrides` -- same router/error-handler wiring as production. Covers both
operations this module owns (`queryAuditLog`, `getAdminReports`). Mirrors
`apps/backend/tests/ads/test_api.py`'s pattern exactly.

Authorization matrix (this module's own contribution): `queryAuditLog` and `getAdminReports` are
gated by TWO DIFFERENT permission keys (`analytics:audit:read`/`analytics:reports:read`) -- a
token authorized for one must NOT be authorized for the other, proven below.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from analytics.application.audit_use_cases import AuditUseCases
from analytics.application.report_use_cases import ReportUseCases
from analytics.domain import AuditEntry
from analytics.interfaces.auth import ActingOperator
from analytics.interfaces.di import (
    get_audit_acting_operator,
    get_audit_use_cases,
    get_report_use_cases,
    get_reports_acting_operator,
)
from main import create_app
from shared_kernel import UserId

from .conftest import FakeAuditEntryRepository, FakeMetricEventRepository

_OPERATOR_ACCOUNT = UserId(value=uuid4())
_AUDIT_TOKENS = {"audit-token", "both-token"}
_REPORTS_TOKENS = {"reports-token", "both-token"}
_UNAUTHORIZED_TOKENS = {"unauthorized-token"}

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _token_from_header(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[len("bearer ") :].strip()
    return None


@pytest.fixture
def client(
    fake_audit_entries: FakeAuditEntryRepository, fake_metric_events: FakeMetricEventRepository
) -> Iterator[TestClient]:
    def _audit_use_cases() -> AuditUseCases:
        return AuditUseCases(entries=fake_audit_entries)

    def _report_use_cases() -> ReportUseCases:
        return ReportUseCases(audit_entries=fake_audit_entries, metrics=fake_metric_events)

    async def audit_acting_operator_override(
        authorization: str | None = Header(default=None),
    ) -> ActingOperator:
        token = _token_from_header(authorization)
        if token in _AUDIT_TOKENS:
            return ActingOperator(account_id=_OPERATOR_ACCOUNT)
        if token in _REPORTS_TOKENS | _UNAUTHORIZED_TOKENS:
            raise HTTPException(status_code=403, detail="caller lacks analytics:audit:read")
        raise HTTPException(status_code=401, detail="no valid session")

    async def reports_acting_operator_override(
        authorization: str | None = Header(default=None),
    ) -> ActingOperator:
        token = _token_from_header(authorization)
        if token in _REPORTS_TOKENS:
            return ActingOperator(account_id=_OPERATOR_ACCOUNT)
        if token in _AUDIT_TOKENS | _UNAUTHORIZED_TOKENS:
            raise HTTPException(status_code=403, detail="caller lacks analytics:reports:read")
        raise HTTPException(status_code=401, detail="no valid session")

    app = create_app()
    app.dependency_overrides[get_audit_use_cases] = _audit_use_cases
    app.dependency_overrides[get_report_use_cases] = _report_use_cases
    app.dependency_overrides[get_audit_acting_operator] = audit_acting_operator_override
    app.dependency_overrides[get_reports_acting_operator] = reports_acting_operator_override

    with TestClient(
        app, base_url="https://testserver", raise_server_exceptions=False
    ) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestQueryAuditLog:
    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.get("/api/v1/admin/audit-log")
        assert response.status_code == 401

    def test_rejects_an_unauthorized_operator(self, client: TestClient) -> None:
        response = client.get("/api/v1/admin/audit-log", headers=_auth("unauthorized-token"))
        assert response.status_code == 403

    def test_a_reports_only_token_cannot_read_the_audit_log(self, client: TestClient) -> None:
        """Proves the two permissions are independently gated -- authorization for
        `getAdminReports` does not imply authorization for `queryAuditLog`."""
        response = client.get("/api/v1/admin/audit-log", headers=_auth("reports-token"))
        assert response.status_code == 403

    def test_returns_a_page_of_entries(
        self, client: TestClient, fake_audit_entries: FakeAuditEntryRepository
    ) -> None:
        fake_audit_entries.entries.append(
            AuditEntry.create(
                action="ModerationActionTaken",
                actor_user_id=None,
                actor_context=None,
                target_type="Listing",
                target_id=uuid4(),
                payload={"action": "HIDE"},
                source_event_id=uuid4(),
                occurred_at=_NOW,
            )
        )
        response = client.get("/api/v1/admin/audit-log", headers=_auth("audit-token"))
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["action"] == "ModerationActionTaken"
        assert "page" in body

    def test_filters_by_action(
        self, client: TestClient, fake_audit_entries: FakeAuditEntryRepository
    ) -> None:
        fake_audit_entries.entries.extend(
            [
                AuditEntry.create(
                    action="PaymentConfirmed",
                    actor_user_id=None,
                    actor_context=None,
                    target_type="Invoice",
                    target_id=uuid4(),
                    payload={},
                    source_event_id=uuid4(),
                    occurred_at=_NOW,
                ),
                AuditEntry.create(
                    action="ModerationActionTaken",
                    actor_user_id=None,
                    actor_context=None,
                    target_type="Listing",
                    target_id=uuid4(),
                    payload={},
                    source_event_id=uuid4(),
                    occurred_at=_NOW,
                ),
            ]
        )
        response = client.get(
            "/api/v1/admin/audit-log",
            params={"action": "PaymentConfirmed"},
            headers=_auth("audit-token"),
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["action"] == "PaymentConfirmed"


class TestGetAdminReports:
    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.get("/api/v1/admin/reports", params={"report": "LISTINGS_OVERVIEW"})
        assert response.status_code == 401

    def test_rejects_an_unauthorized_operator(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/admin/reports",
            params={"report": "LISTINGS_OVERVIEW"},
            headers=_auth("unauthorized-token"),
        )
        assert response.status_code == 403

    def test_an_audit_only_token_cannot_read_reports(self, client: TestClient) -> None:
        """Proves the two permissions are independently gated -- authorization for
        `queryAuditLog` does not imply authorization for `getAdminReports`."""
        response = client.get(
            "/api/v1/admin/reports",
            params={"report": "LISTINGS_OVERVIEW"},
            headers=_auth("audit-token"),
        )
        assert response.status_code == 403

    def test_returns_a_report_dataset(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/admin/reports",
            params={"report": "MODERATION_THROUGHPUT"},
            headers=_auth("reports-token"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["report"] == "MODERATION_THROUGHPUT"

    def test_rejects_an_unknown_report_key(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/admin/reports",
            params={"report": "NOT_A_REAL_REPORT"},
            headers=_auth("reports-token"),
        )
        assert response.status_code in (400, 422)
