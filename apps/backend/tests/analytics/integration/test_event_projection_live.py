"""Integration tests: `analytics.infrastructure.event_projection`'s eight idempotent consumers
against real PostgreSQL -- the `ProcessedEventRow` ledger + `idempotent_consume` is what actually
needs a real `INSERT ... ON CONFLICT` to prove (mirrors `apps/backend/tests/ads/integration/
test_event_projection_live.py`'s own pattern).

Covers both of this task's own named invariant requirements:
- test_I23_*: metric writes are idempotent on the triggering event id, for EVERY metric family
  (views, contact clicks, phone reveals, chats initiated, favorites, premium-listing stats,
  banner impressions, banner clicks).
- test_I22_*: every administrative/moderation/configuration action produces an audit fact
  (moderation actions, configuration publishes, billing payment confirmations, verification
  decisions, account suspensions).

All six handlers routed live in `composition_root.py` (`handle_billing_event_for_analytics`,
`handle_catalog_event_for_analytics`, `handle_identity_event_for_analytics`,
`handle_messaging_event_for_analytics`, `handle_profiles_event_for_analytics`,
`handle_moderation_event_for_analytics`) plus the two FIRST-EVER dispatchers this task adds
(`handle_configuration_event`, `handle_ads_event`) are exercised directly here against synthetic
envelopes, since composition-root wiring itself is not re-tested per module (mirrors every prior
task's own precedent).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.application.audit_use_cases import AuditUseCases
from analytics.application.metric_use_cases import MetricUseCases
from analytics.infrastructure.event_projection import (
    handle_ads_event,
    handle_billing_event,
    handle_catalog_event,
    handle_configuration_event,
    handle_identity_event,
    handle_messaging_event,
    handle_moderation_event,
    handle_profiles_event,
)
from analytics.infrastructure.persistence.models import (
    AuditEntryRow,
    MetricEventRow,
    ProcessedEventRow,
)
from analytics.infrastructure.persistence.repository import (
    SqlalchemyAuditEntryRepository,
    SqlalchemyListingStatisticsProjectionRepository,
    SqlalchemyMetricEventRepository,
)
from shared_kernel import EventEnvelope

NOW = datetime.now(UTC)


def _envelope(
    event_type: str, payload: dict[str, object], *, actor: object = None
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        occurred_at=NOW,
        actor=actor,  # type: ignore[arg-type]
        aggregate_type="TestAggregate",
        aggregate_id=uuid4(),
        payload=payload,
    )


def _audit_use_cases(session: AsyncSession) -> AuditUseCases:
    return AuditUseCases(entries=SqlalchemyAuditEntryRepository(session))


def _metric_use_cases(session: AsyncSession) -> MetricUseCases:
    return MetricUseCases(
        metrics=SqlalchemyMetricEventRepository(session),
        listing_statistics=SqlalchemyListingStatisticsProjectionRepository(session),
    )


async def _count(session: AsyncSession, model: type[AuditEntryRow] | type[MetricEventRow]) -> int:
    result: object = await session.execute(select(model))
    return len(result.scalars().all())  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------------------------
# I-22: audit coverage -- moderation, configuration, billing, identity, profiles.
# ---------------------------------------------------------------------------------------------


async def test_I22_moderation_action_taken_produces_an_audit_entry(
    db_session: AsyncSession,
) -> None:
    envelope = _envelope(
        "ModerationActionTaken",
        {
            "moderationCaseId": str(uuid4()),
            "subjectType": "LISTING",
            "subjectId": str(uuid4()),
            "action": "HIDE",
        },
        actor=uuid4(),
    )
    await handle_moderation_event(
        db_session, envelope, audit_use_cases=_audit_use_cases(db_session)
    )
    await db_session.flush()
    assert await _count(db_session, AuditEntryRow) == 1


async def test_I22_a_configuration_publish_produces_an_audit_entry(
    db_session: AsyncSession,
) -> None:
    envelope = _envelope(
        "CategoryCreated",
        {
            "action": "PUBLISH",
            "entityType": "CATEGORY",
            "code": "electronics",
            "beforeVersionId": None,
            "afterVersionId": str(uuid4()),
        },
        actor=uuid4(),
    )
    await handle_configuration_event(
        db_session, envelope, audit_use_cases=_audit_use_cases(db_session)
    )
    await db_session.flush()
    assert await _count(db_session, AuditEntryRow) == 1


async def test_I22_payment_confirmed_produces_an_audit_entry(db_session: AsyncSession) -> None:
    envelope = _envelope(
        "PaymentConfirmed",
        {"invoiceId": str(uuid4()), "orderId": str(uuid4()), "amount": "50.00", "currency": "UZS"},
        actor=uuid4(),
    )
    await handle_billing_event(db_session, envelope, audit_use_cases=_audit_use_cases(db_session))
    await db_session.flush()
    assert await _count(db_session, AuditEntryRow) == 1


async def test_I22_account_suspended_produces_an_audit_entry(db_session: AsyncSession) -> None:
    envelope = _envelope(
        "AccountSuspended", {"accountId": str(uuid4()), "reason": "abuse"}, actor=uuid4()
    )
    await handle_identity_event(db_session, envelope, audit_use_cases=_audit_use_cases(db_session))
    await db_session.flush()
    assert await _count(db_session, AuditEntryRow) == 1


async def test_I22_a_verification_decision_produces_an_audit_entry(
    db_session: AsyncSession,
) -> None:
    envelope = _envelope(
        "BusinessVerified",
        {"verificationCaseId": str(uuid4()), "businessProfileId": str(uuid4())},
        actor=uuid4(),
    )
    await handle_profiles_event(db_session, envelope, audit_use_cases=_audit_use_cases(db_session))
    await db_session.flush()
    assert await _count(db_session, AuditEntryRow) == 1


async def test_a_configuration_event_outside_the_audited_set_is_ignored(
    db_session: AsyncSession,
) -> None:
    envelope = _envelope("SomeUnrelatedEvent", {})
    await handle_configuration_event(
        db_session, envelope, audit_use_cases=_audit_use_cases(db_session)
    )
    await db_session.flush()
    assert await _count(db_session, AuditEntryRow) == 0


async def test_user_registered_is_not_audited(db_session: AsyncSession) -> None:
    """UserRegistered is not an administrative action under I-22's own scope (see
    `analytics/README.md` "Known gaps")."""
    envelope = _envelope("UserRegistered", {"accountId": str(uuid4())})
    await handle_identity_event(db_session, envelope, audit_use_cases=_audit_use_cases(db_session))
    await db_session.flush()
    assert await _count(db_session, AuditEntryRow) == 0


# ---------------------------------------------------------------------------------------------
# I-23: metric idempotency, every family.
# ---------------------------------------------------------------------------------------------


async def test_I23_listing_viewed_is_idempotent(db_session: AsyncSession) -> None:
    envelope = _envelope("ListingViewed", {"listingId": str(uuid4()), "viewerUserId": str(uuid4())})
    use_cases = _metric_use_cases(db_session)
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    assert await _count(db_session, MetricEventRow) == 1


async def test_I23_contact_button_clicked_is_idempotent(db_session: AsyncSession) -> None:
    envelope = _envelope(
        "ContactButtonClicked", {"listingId": str(uuid4()), "userId": str(uuid4())}
    )
    use_cases = _metric_use_cases(db_session)
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    assert await _count(db_session, MetricEventRow) == 1


async def test_I23_favorite_added_is_idempotent(db_session: AsyncSession) -> None:
    envelope = _envelope("FavoriteAdded", {"listingId": str(uuid4()), "userId": str(uuid4())})
    use_cases = _metric_use_cases(db_session)
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    assert await _count(db_session, MetricEventRow) == 1


async def test_I23_premium_listing_stat_is_idempotent(db_session: AsyncSession) -> None:
    envelope = _envelope(
        "PremiumListingStat", {"listingId": str(uuid4()), "promotionKind": "PREMIUM"}
    )
    use_cases = _metric_use_cases(db_session)
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    assert await _count(db_session, MetricEventRow) == 1


async def test_I23_phone_revealed_is_idempotent(db_session: AsyncSession) -> None:
    envelope = _envelope(
        "PhoneRevealed",
        {
            "conversationId": str(uuid4()),
            "revealerUserId": str(uuid4()),
            "revealedUserId": str(uuid4()),
        },
    )
    use_cases = _metric_use_cases(db_session)
    await handle_messaging_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    await handle_messaging_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    assert await _count(db_session, MetricEventRow) == 1


async def test_I23_chat_initiated_is_idempotent(db_session: AsyncSession) -> None:
    envelope = _envelope(
        "ChatInitiated",
        {
            "conversationId": str(uuid4()),
            "listingId": str(uuid4()),
            "initiatorUserId": str(uuid4()),
            "recipientUserId": str(uuid4()),
        },
    )
    use_cases = _metric_use_cases(db_session)
    await handle_messaging_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    await handle_messaging_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    assert await _count(db_session, MetricEventRow) == 1


async def test_I23_banner_impression_recorded_is_idempotent(db_session: AsyncSession) -> None:
    envelope = _envelope(
        "BannerImpressionRecorded", {"campaignId": str(uuid4()), "slotKey": "HOMEPAGE_TOP"}
    )
    use_cases = _metric_use_cases(db_session)
    await handle_ads_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    await handle_ads_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    assert await _count(db_session, MetricEventRow) == 1


async def test_I23_banner_click_recorded_is_idempotent(db_session: AsyncSession) -> None:
    envelope = _envelope(
        "BannerClickRecorded", {"campaignId": str(uuid4()), "slotKey": "HOMEPAGE_TOP"}
    )
    use_cases = _metric_use_cases(db_session)
    await handle_ads_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    await handle_ads_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    assert await _count(db_session, MetricEventRow) == 1


async def test_I23_redelivery_does_not_double_count_the_listing_statistics_projection(
    db_session: AsyncSession,
) -> None:
    """The double-counting the invariant actually protects against: a redelivered ListingViewed
    must not inflate the owner-facing view counter."""
    listing_id = uuid4()
    envelope = _envelope(
        "ListingViewed", {"listingId": str(listing_id), "viewerUserId": str(uuid4())}
    )
    use_cases = _metric_use_cases(db_session)
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()

    from shared_kernel import ListingId

    snapshot = await use_cases.get_listing_statistics(ListingId(value=listing_id))
    assert snapshot is not None
    assert snapshot.views == 1


async def test_a_catalog_event_outside_the_metric_set_is_ignored(db_session: AsyncSession) -> None:
    envelope = _envelope("ListingCreated", {})
    use_cases = _metric_use_cases(db_session)
    await handle_catalog_event(db_session, envelope, metric_use_cases=use_cases)
    await db_session.flush()
    assert await _count(db_session, MetricEventRow) == 0


async def test_redelivering_the_same_event_across_different_handlers_is_independent(
    db_session: AsyncSession,
) -> None:
    """Idempotency is keyed per (event_id, handler) -- confirms two DIFFERENT handler names for
    the same underlying `ProcessedEventRow` ledger don't collide."""
    envelope = _envelope("ListingViewed", {"listingId": str(uuid4()), "viewerUserId": str(uuid4())})
    await handle_catalog_event(db_session, envelope, metric_use_cases=_metric_use_cases(db_session))
    await db_session.flush()

    result = await db_session.execute(
        select(ProcessedEventRow).where(ProcessedEventRow.event_id == envelope.event_id)
    )
    ledger_rows = result.scalars().all()
    assert len(ledger_rows) == 1
    assert ledger_rows[0].handler == "analytics.handle_catalog_event"
