"""Unit tests for `ReportUseCases` (FR-ADMIN-005, BRULE-20) -- the fixed five-report v1 set."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from analytics.application.exceptions import UnknownReportError
from analytics.application.report_use_cases import ReportUseCases
from analytics.domain import AuditEntry, MetricEvent
from shared_kernel import ListingId

from .conftest import FakeAuditEntryRepository, FakeMetricEventRepository

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _use_cases(
    audit_entries: FakeAuditEntryRepository, metrics: FakeMetricEventRepository
) -> ReportUseCases:
    return ReportUseCases(audit_entries=audit_entries, metrics=metrics)


@pytest.mark.asyncio
async def test_listings_overview_counts_engagement_metrics(
    fake_audit_entries: FakeAuditEntryRepository, fake_metric_events: FakeMetricEventRepository
) -> None:
    fake_metric_events.events = [
        MetricEvent.create(
            metric_key="LISTING_VIEWED",
            listing_id=ListingId(value=uuid4()),
            user_id=None,
            campaign_id=None,
            payload={},
            source_event_id=uuid4(),
            occurred_at=_NOW,
        ),
        MetricEvent.create(
            metric_key="LISTING_VIEWED",
            listing_id=ListingId(value=uuid4()),
            user_id=None,
            campaign_id=None,
            payload={},
            source_event_id=uuid4(),
            occurred_at=_NOW,
        ),
        MetricEvent.create(
            metric_key="FAVORITE_ADDED",
            listing_id=ListingId(value=uuid4()),
            user_id=None,
            campaign_id=None,
            payload={},
            source_event_id=uuid4(),
            occurred_at=_NOW,
        ),
    ]
    use_cases = _use_cases(fake_audit_entries, fake_metric_events)
    report = await use_cases.get_admin_reports(
        report="LISTINGS_OVERVIEW", occurred_from=None, occurred_to=None
    )
    assert report["counts"]["LISTING_VIEWED"] == 2
    assert report["counts"]["FAVORITE_ADDED"] == 1
    assert report["total"] == 3


@pytest.mark.asyncio
async def test_UNF_030_listings_overview_enumerates_all_eight_closed_metrics(
    fake_audit_entries: FakeAuditEntryRepository, fake_metric_events: FakeMetricEventRepository
) -> None:
    """BRULE-20/BC-13 define a closed set of EIGHT metric keys; `counts` used to enumerate only
    six, silently omitting the two banner metrics even though the event projection already
    records them."""
    use_cases = _use_cases(fake_audit_entries, fake_metric_events)
    report = await use_cases.get_admin_reports(
        report="LISTINGS_OVERVIEW", occurred_from=None, occurred_to=None
    )
    assert set(report["counts"]) == {
        "LISTING_VIEWED",
        "CONTACT_BUTTON_CLICKED",
        "PHONE_REVEALED",
        "CHAT_INITIATED",
        "FAVORITE_ADDED",
        "PREMIUM_LISTING_STAT",
        "BANNER_IMPRESSION_RECORDED",
        "BANNER_CLICK_RECORDED",
    }


@pytest.mark.asyncio
async def test_user_growth_reports_unavailable_honestly(
    fake_audit_entries: FakeAuditEntryRepository, fake_metric_events: FakeMetricEventRepository
) -> None:
    """No data source exists for USER_GROWTH in v1 -- an honest empty dataset, never a
    fabricated count."""
    use_cases = _use_cases(fake_audit_entries, fake_metric_events)
    report = await use_cases.get_admin_reports(
        report="USER_GROWTH", occurred_from=None, occurred_to=None
    )
    assert report["available"] is False


@pytest.mark.asyncio
async def test_revenue_sums_confirmed_payments_by_currency(
    fake_audit_entries: FakeAuditEntryRepository, fake_metric_events: FakeMetricEventRepository
) -> None:
    use_cases = _use_cases(fake_audit_entries, fake_metric_events)
    await fake_audit_entries.add(
        AuditEntry.create(
            action="PaymentConfirmed",
            actor_user_id=None,
            actor_context=None,
            target_type="Invoice",
            target_id=uuid4(),
            payload={"amount": "100.00", "currency": "UZS"},
            source_event_id=uuid4(),
            occurred_at=_NOW,
        )
    )
    report = await use_cases.get_admin_reports(
        report="REVENUE", occurred_from=None, occurred_to=None
    )
    assert report["confirmedPayments"] == 1
    assert report["totalsByCurrency"] == {"UZS": 100.0}


@pytest.mark.asyncio
async def test_verification_sla_counts_approved_and_rejected(
    fake_audit_entries: FakeAuditEntryRepository, fake_metric_events: FakeMetricEventRepository
) -> None:

    await fake_audit_entries.add(
        AuditEntry.create(
            action="BusinessVerified",
            actor_user_id=None,
            actor_context=None,
            target_type="VerificationCase",
            target_id=uuid4(),
            payload={},
            source_event_id=uuid4(),
            occurred_at=_NOW,
        )
    )
    await fake_audit_entries.add(
        AuditEntry.create(
            action="VerificationRejected",
            actor_user_id=None,
            actor_context=None,
            target_type="VerificationCase",
            target_id=uuid4(),
            payload={},
            source_event_id=uuid4(),
            occurred_at=_NOW,
        )
    )
    use_cases = _use_cases(fake_audit_entries, fake_metric_events)
    report = await use_cases.get_admin_reports(
        report="VERIFICATION_SLA", occurred_from=None, occurred_to=None
    )
    assert report["approved"] == 1
    assert report["rejected"] == 1
    assert report["decisions"] == 2


@pytest.mark.asyncio
async def test_moderation_throughput_groups_by_verb(
    fake_audit_entries: FakeAuditEntryRepository, fake_metric_events: FakeMetricEventRepository
) -> None:

    await fake_audit_entries.add(
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
    await fake_audit_entries.add(
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
    use_cases = _use_cases(fake_audit_entries, fake_metric_events)
    report = await use_cases.get_admin_reports(
        report="MODERATION_THROUGHPUT", occurred_from=None, occurred_to=None
    )
    assert report["byVerb"] == {"HIDE": 2}
    assert report["actionsTaken"] == 2


@pytest.mark.asyncio
async def test_unknown_report_raises(
    fake_audit_entries: FakeAuditEntryRepository, fake_metric_events: FakeMetricEventRepository
) -> None:
    use_cases = _use_cases(fake_audit_entries, fake_metric_events)
    with pytest.raises(UnknownReportError):
        await use_cases.get_admin_reports(
            report="NOT_A_REPORT", occurred_from=None, occurred_to=None
        )
