"""Shared fixtures for admin's fast (no-DB) unit + API tests: in-memory fakes for `admin`'s one
repository port, and tiny fakes satisfying `AdminDashboardUseCases`' four narrow probe Protocols
-- mirrors `apps/backend/tests/ads/conftest.py`'s pattern exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from admin.domain import OperatorSessionContext
from shared_kernel import UserId


@dataclass
class FakeOperatorSessionRepository:
    """Implements `admin.application.ports.OperatorSessionRepository`."""

    rows: dict[UserId, OperatorSessionContext] = field(default_factory=dict)

    async def get_by_operator(self, operator_user_id: UserId) -> OperatorSessionContext | None:
        return self.rows.get(operator_user_id)

    async def upsert(
        self, *, operator_user_id: UserId, context: dict[str, Any], now: datetime
    ) -> OperatorSessionContext:
        existing = self.rows.get(operator_user_id)
        updated = (
            existing.with_context(context=context, now=now)
            if existing is not None
            else OperatorSessionContext.create(
                operator_user_id=operator_user_id, context=context, now=now
            )
        )
        self.rows[operator_user_id] = updated
        return updated


class _CallRecorder:
    """Shared call-tracking base -- each probe fake below records the `(status, limit)` it was
    called with, so tests can assert the dashboard actually reaches every one of its four probes,
    without caring about the (deliberately unused, see `dashboard_use_cases.py`) return value."""

    def __init__(self) -> None:
        self.calls: list[tuple[str | None, int | None]] = []


class FakeModerationQueueProbe(_CallRecorder):
    """Implements `admin.application.dashboard_use_cases._ModerationQueueProbe`."""

    async def list_moderation_queue(
        self, status: str | None = None, limit: int | None = 20
    ) -> object:
        self.calls.append((status, limit))
        return object()


class FakeVerificationQueueProbe(_CallRecorder):
    """Implements `admin.application.dashboard_use_cases._VerificationQueueProbe`."""

    async def list_verification_queue(
        self, status: str | None = None, limit: int | None = 20
    ) -> object:
        self.calls.append((status, limit))
        return object()


class FakeInvoiceQueueProbe(_CallRecorder):
    """Implements `admin.application.dashboard_use_cases._InvoiceQueueProbe`."""

    async def admin_list_invoices(
        self, status: str | None = None, limit: int | None = 20
    ) -> object:
        self.calls.append((status, limit))
        return object()


class FakeUserQueueProbe(_CallRecorder):
    """Implements `admin.application.dashboard_use_cases._UserQueueProbe`."""

    async def admin_list_users(self, status: str | None = None, limit: int | None = 20) -> object:
        self.calls.append((status, limit))
        return object()


@pytest.fixture
def fake_operator_sessions() -> FakeOperatorSessionRepository:
    return FakeOperatorSessionRepository()


@pytest.fixture
def fake_moderation_probe() -> FakeModerationQueueProbe:
    return FakeModerationQueueProbe()


@pytest.fixture
def fake_verification_probe() -> FakeVerificationQueueProbe:
    return FakeVerificationQueueProbe()


@pytest.fixture
def fake_invoice_probe() -> FakeInvoiceQueueProbe:
    return FakeInvoiceQueueProbe()


@pytest.fixture
def fake_user_probe() -> FakeUserQueueProbe:
    return FakeUserQueueProbe()
