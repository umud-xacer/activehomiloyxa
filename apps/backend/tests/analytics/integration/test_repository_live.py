"""Integration tests: `SqlalchemyAuditEntryRepository`/`SqlalchemyMetricEventRepository`/
`SqlalchemyListingStatisticsProjectionRepository` round-trip against real PostgreSQL, including
the physical `metric_key` CHECK constraint and the immutability guard triggers (PD-07) -- proven
independently of the domain-level guard already tested in `test_audit_entry.py`/
`test_metric_event.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.domain import AuditEntry, MetricEvent, MetricKey
from analytics.infrastructure.persistence.repository import (
    SqlalchemyAuditEntryRepository,
    SqlalchemyListingStatisticsProjectionRepository,
    SqlalchemyMetricEventRepository,
)
from shared_kernel import ListingId, UserId

NOW = datetime.now(UTC)


def _audit_entry(**overrides: object) -> AuditEntry:
    defaults: dict[str, object] = {
        "action": "ModerationActionTaken",
        "actor_user_id": UserId(value=uuid4()),
        "actor_context": None,
        "target_type": "Listing",
        "target_id": uuid4(),
        "payload": {"action": "HIDE"},
        "source_event_id": uuid4(),
        "occurred_at": NOW,
    }
    defaults.update(overrides)
    return AuditEntry.create(**defaults)  # type: ignore[arg-type]


def _metric_event(**overrides: object) -> MetricEvent:
    defaults: dict[str, object] = {
        "metric_key": "LISTING_VIEWED",
        "listing_id": ListingId(value=uuid4()),
        "user_id": None,
        "campaign_id": None,
        "payload": {},
        "source_event_id": uuid4(),
        "occurred_at": NOW,
    }
    defaults.update(overrides)
    return MetricEvent.create(**defaults)  # type: ignore[arg-type]


async def test_audit_entry_add_then_query_round_trips(db_session: AsyncSession) -> None:
    repo = SqlalchemyAuditEntryRepository(db_session)
    entry = _audit_entry()
    await repo.add(entry)
    await db_session.flush()

    found, _ = await repo.query(
        actor_user_id=None,
        target_type=None,
        action=None,
        occurred_from=None,
        occurred_to=None,
        cursor=None,
        limit=20,
    )
    assert len(found) == 1
    assert found[0].id == entry.id
    assert found[0].action == "ModerationActionTaken"
    assert found[0].payload == {"action": "HIDE"}


async def test_audit_entry_query_filters_by_action(db_session: AsyncSession) -> None:
    repo = SqlalchemyAuditEntryRepository(db_session)
    await repo.add(_audit_entry(action="PaymentConfirmed"))
    await repo.add(_audit_entry(action="ModerationActionTaken"))
    await db_session.flush()

    found, _ = await repo.query(
        actor_user_id=None,
        target_type=None,
        action="PaymentConfirmed",
        occurred_from=None,
        occurred_to=None,
        cursor=None,
        limit=20,
    )
    assert len(found) == 1
    assert found[0].action == "PaymentConfirmed"


async def test_audit_entry_query_paginates_with_a_cursor(db_session: AsyncSession) -> None:
    repo = SqlalchemyAuditEntryRepository(db_session)
    for i in range(3):
        await repo.add(_audit_entry(occurred_at=NOW + timedelta(seconds=i)))
    await db_session.flush()

    page_one, cursor = await repo.query(
        actor_user_id=None,
        target_type=None,
        action=None,
        occurred_from=None,
        occurred_to=None,
        cursor=None,
        limit=2,
    )
    assert len(page_one) == 2
    assert cursor is not None

    page_two, next_cursor = await repo.query(
        actor_user_id=None,
        target_type=None,
        action=None,
        occurred_from=None,
        occurred_to=None,
        cursor=cursor,
        limit=2,
    )
    assert len(page_two) == 1
    assert next_cursor is None


async def test_audit_entry_list_for_report_scopes_by_action_and_date(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyAuditEntryRepository(db_session)
    await repo.add(_audit_entry(action="PaymentConfirmed", occurred_at=NOW - timedelta(days=10)))
    recent = _audit_entry(action="PaymentConfirmed", occurred_at=NOW)
    await repo.add(recent)
    await db_session.flush()

    found = await repo.list_for_report(
        actions=("PaymentConfirmed",), occurred_from=NOW - timedelta(days=1), occurred_to=None
    )
    assert [e.id for e in found] == [recent.id]


async def test_metric_event_add_then_list_all_ordered_round_trips(db_session: AsyncSession) -> None:
    repo = SqlalchemyMetricEventRepository(db_session)
    metric = _metric_event()
    await repo.add(metric)
    await db_session.flush()

    found = await repo.list_all_ordered()
    assert len(found) == 1
    assert found[0].id == metric.id
    assert found[0].metric_key == metric.metric_key


async def test_metric_event_list_for_report_scopes_by_key(db_session: AsyncSession) -> None:
    repo = SqlalchemyMetricEventRepository(db_session)
    await repo.add(_metric_event(metric_key="LISTING_VIEWED"))
    await repo.add(_metric_event(metric_key="FAVORITE_ADDED"))
    await db_session.flush()

    found = await repo.list_for_report(
        metric_keys=(MetricKey.FAVORITE_ADDED,), occurred_from=None, occurred_to=None
    )
    assert len(found) == 1
    assert found[0].metric_key == MetricKey.FAVORITE_ADDED


async def test_listing_statistics_apply_metric_then_get_round_trips(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyListingStatisticsProjectionRepository(db_session)
    listing_id = ListingId(value=uuid4())
    metric = _metric_event(metric_key="LISTING_VIEWED", listing_id=listing_id)

    await repo.apply_metric(metric, position=1)
    await db_session.flush()

    snapshot = await repo.get_by_listing_id(listing_id)
    assert snapshot is not None
    assert snapshot.views == 1
    assert snapshot.as_of_position == 1


async def test_listing_statistics_reset_clears_all_rows(db_session: AsyncSession) -> None:
    repo = SqlalchemyListingStatisticsProjectionRepository(db_session)
    listing_id = ListingId(value=uuid4())
    await repo.apply_metric(
        _metric_event(metric_key="FAVORITE_ADDED", listing_id=listing_id), position=1
    )
    await db_session.flush()

    await repo.reset()
    await db_session.flush()

    assert await repo.get_by_listing_id(listing_id) is None


async def test_listing_statistics_checkpoint_defaults_to_zero_then_advances(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyListingStatisticsProjectionRepository(db_session)
    assert await repo.checkpoint_position() == 0
    await repo.advance_checkpoint(5)
    await db_session.flush()
    assert await repo.checkpoint_position() == 5


# I-22/I-23 at the DATABASE level (PD-07 guard trigger) -- independent of the domain-level guard.
async def test_I22_the_database_rejects_an_update_to_a_stored_audit_entry(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyAuditEntryRepository(db_session)
    entry = _audit_entry()
    await repo.add(entry)
    await db_session.flush()

    with pytest.raises(DBAPIError, match="immutability guard"):
        await db_session.execute(
            text(
                "UPDATE analytics.audit_entry SET action = 'Tampered' "
                "WHERE id = :id AND occurred_at = :occurred_at"
            ),
            {"id": entry.id, "occurred_at": entry.occurred_at},
        )


async def test_I22_the_database_rejects_a_delete_of_a_stored_audit_entry(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyAuditEntryRepository(db_session)
    entry = _audit_entry()
    await repo.add(entry)
    await db_session.flush()

    with pytest.raises(DBAPIError, match="immutability guard"):
        await db_session.execute(
            text("DELETE FROM analytics.audit_entry WHERE id = :id AND occurred_at = :occurred_at"),
            {"id": entry.id, "occurred_at": entry.occurred_at},
        )


async def test_I23_the_database_rejects_an_update_to_a_stored_metric_event(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyMetricEventRepository(db_session)
    metric = _metric_event()
    await repo.add(metric)
    await db_session.flush()

    with pytest.raises(DBAPIError, match="immutability guard"):
        await db_session.execute(
            text(
                "UPDATE analytics.metric_event SET metric_key = 'FAVORITE_ADDED' "
                "WHERE id = :id AND occurred_at = :occurred_at"
            ),
            {"id": metric.id, "occurred_at": metric.occurred_at},
        )


async def test_I23_the_database_rejects_a_delete_of_a_stored_metric_event(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyMetricEventRepository(db_session)
    metric = _metric_event()
    await repo.add(metric)
    await db_session.flush()

    with pytest.raises(DBAPIError, match="immutability guard"):
        await db_session.execute(
            text(
                "DELETE FROM analytics.metric_event WHERE id = :id AND occurred_at = :occurred_at"
            ),
            {"id": metric.id, "occurred_at": metric.occurred_at},
        )


async def test_closed_vocabulary_check_constraint_rejects_an_unknown_metric_key(
    db_session: AsyncSession,
) -> None:
    """# enforces I-23/BRULE-20 at the PHYSICAL layer too -- a raw INSERT bypassing the domain
    entirely is still rejected by `ck_metric_event_metric_key`."""
    with pytest.raises(DBAPIError, match="ck_metric_event_metric_key"):
        await db_session.execute(
            text(
                "INSERT INTO analytics.metric_event "
                "(id, occurred_at, metric_key, payload, source_event_id) "
                "VALUES (:id, :occurred_at, 'NOT_A_REAL_KEY', '{}'::jsonb, :source_event_id)"
            ),
            {"id": uuid4(), "occurred_at": NOW, "source_event_id": uuid4()},
        )
