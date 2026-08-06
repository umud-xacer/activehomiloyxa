"""Unit tests for `AuditUseCases` (FR-AUDIT-001/002, I-22)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from analytics.application.audit_use_cases import AuditUseCases
from shared_kernel import UserId

from .conftest import FakeAuditEntryRepository

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


@pytest.mark.asyncio
async def test_record_audit_fact_persists_the_entry(
    fake_audit_entries: FakeAuditEntryRepository,
) -> None:
    use_cases = AuditUseCases(entries=fake_audit_entries)
    actor = UserId(value=uuid4())
    entry = await use_cases.record_audit_fact(
        action="ModerationActionTaken",
        actor_user_id=actor,
        actor_context=None,
        target_type="Listing",
        target_id=uuid4(),
        payload={"action": "HIDE"},
        source_event_id=uuid4(),
        occurred_at=_NOW,
    )
    assert entry.action == "ModerationActionTaken"
    assert fake_audit_entries.entries == [entry]


@pytest.mark.asyncio
async def test_query_audit_log_filters_by_action(
    fake_audit_entries: FakeAuditEntryRepository,
) -> None:
    use_cases = AuditUseCases(entries=fake_audit_entries)
    await use_cases.record_audit_fact(
        action="PaymentConfirmed",
        actor_user_id=None,
        actor_context=None,
        target_type="Invoice",
        target_id=uuid4(),
        payload={},
        source_event_id=uuid4(),
        occurred_at=_NOW,
    )
    await use_cases.record_audit_fact(
        action="ModerationActionTaken",
        actor_user_id=None,
        actor_context=None,
        target_type="Listing",
        target_id=uuid4(),
        payload={},
        source_event_id=uuid4(),
        occurred_at=_NOW + timedelta(minutes=1),
    )
    entries, _ = await use_cases.query_audit_log(action="PaymentConfirmed")
    assert len(entries) == 1
    assert entries[0].action == "PaymentConfirmed"


@pytest.mark.asyncio
async def test_query_audit_log_filters_by_date_range(
    fake_audit_entries: FakeAuditEntryRepository,
) -> None:
    use_cases = AuditUseCases(entries=fake_audit_entries)
    await use_cases.record_audit_fact(
        action="ModerationActionTaken",
        actor_user_id=None,
        actor_context=None,
        target_type=None,
        target_id=None,
        payload={},
        source_event_id=uuid4(),
        occurred_at=_NOW - timedelta(days=10),
    )
    recent = await use_cases.record_audit_fact(
        action="ModerationActionTaken",
        actor_user_id=None,
        actor_context=None,
        target_type=None,
        target_id=None,
        payload={},
        source_event_id=uuid4(),
        occurred_at=_NOW,
    )
    entries, _ = await use_cases.query_audit_log(occurred_from=_NOW - timedelta(days=1))
    assert entries == [recent]
