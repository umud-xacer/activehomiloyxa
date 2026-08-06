"""API-shape test against the real FastAPI app (`main.create_app`), with the composition root's
real acting-operator/dashboard providers swapped for in-memory fakes via
`app.dependency_overrides` -- same router/error-handler wiring as production. Covers the one
Administration-tagged operation genuinely admin's own (`getAdminDashboard`); the authorization
default-deny proof this task's own validation checklist requires. Mirrors
`apps/backend/tests/ads/test_api.py`'s pattern exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from admin.application.dashboard_use_cases import AdminDashboardUseCases
from admin.interfaces.auth import ActingOperator
from admin.interfaces.di import get_acting_operator, get_dashboard_use_cases
from main import create_app
from shared_kernel import UserId

from .conftest import (
    FakeInvoiceQueueProbe,
    FakeModerationQueueProbe,
    FakeUserQueueProbe,
    FakeVerificationQueueProbe,
)

_OPERATOR_ACCOUNT = UserId(value=uuid4())
_OPERATOR_TOKENS = {"operator-token"}
_UNAUTHORIZED_TOKENS = {"unauthorized-token"}


@pytest.fixture
def client(
    fake_moderation_probe: FakeModerationQueueProbe,
    fake_verification_probe: FakeVerificationQueueProbe,
    fake_invoice_probe: FakeInvoiceQueueProbe,
    fake_user_probe: FakeUserQueueProbe,
) -> Iterator[TestClient]:
    def _dashboard_use_cases() -> AdminDashboardUseCases:
        return AdminDashboardUseCases(
            moderation=fake_moderation_probe,
            verification=fake_verification_probe,
            orders=fake_invoice_probe,
            users=fake_user_probe,
        )

    async def acting_operator_override(
        authorization: str | None = Header(default=None),
    ) -> ActingOperator:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[len("bearer ") :].strip()
        if token in _OPERATOR_TOKENS:
            return ActingOperator(account_id=_OPERATOR_ACCOUNT)
        if token in _UNAUTHORIZED_TOKENS:
            raise HTTPException(status_code=403, detail="caller lacks admin:dashboard:read")
        raise HTTPException(status_code=401, detail="no valid session")

    app = create_app()
    app.dependency_overrides[get_dashboard_use_cases] = _dashboard_use_cases
    app.dependency_overrides[get_acting_operator] = acting_operator_override

    with TestClient(
        app, base_url="https://testserver", raise_server_exceptions=False
    ) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestGetAdminDashboard:
    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.get("/api/v1/admin/dashboard")
        assert response.status_code == 401

    def test_default_denies_a_caller_without_admin_dashboard_read(self, client: TestClient) -> None:
        response = client.get("/api/v1/admin/dashboard", headers=_auth("unauthorized-token"))
        assert response.status_code == 403

    def test_returns_the_honest_null_summary_for_an_authorized_operator(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/v1/admin/dashboard", headers=_auth("operator-token"))
        assert response.status_code == 200
        assert response.json() == {
            "activeListings": None,
            "pendingModeration": None,
            "pendingVerification": None,
            "pendingInvoices": None,
            "newUsers7d": None,
        }

    def test_composes_through_all_four_probes_for_a_real_authorized_call(
        self,
        client: TestClient,
        fake_moderation_probe: FakeModerationQueueProbe,
        fake_verification_probe: FakeVerificationQueueProbe,
        fake_invoice_probe: FakeInvoiceQueueProbe,
        fake_user_probe: FakeUserQueueProbe,
    ) -> None:
        client.get("/api/v1/admin/dashboard", headers=_auth("operator-token"))

        assert fake_moderation_probe.calls
        assert fake_verification_probe.calls
        assert fake_invoice_probe.calls
        assert fake_user_probe.calls
