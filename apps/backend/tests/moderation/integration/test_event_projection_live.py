"""Integration tests: `moderation.infrastructure.event_projection`'s idempotent consumers
against real PostgreSQL -- the `ProcessedEventRow` ledger + `idempotent_consume` is what actually
needs a real `INSERT ... ON CONFLICT` to prove, mirroring `apps/backend/tests/catalog/
integration/test_event_projection_live.py`'s own pattern (Logical Sec 18 "idempotency is data").
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from moderation.application.action_service import ModerationActionService
from moderation.application.moderation_use_cases import ModerationUseCases
from moderation.domain import CaseStatus, SubjectType
from moderation.infrastructure.event_projection import (
    handle_content_reported,
    handle_listing_flagged,
)
from moderation.infrastructure.persistence.models import (
    OutboxEventRow,
    ProcessedEventRow,
)
from moderation.infrastructure.persistence.repository import (
    SqlalchemyModerationCaseRepository,
)
from shared_kernel import EventEnvelope

from ..conftest import (
    FakeAccountSuspensionCommandPort,
    FakeListingModerationCommandPort,
    FakeProfileModerationCommandPort,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _use_cases(session: AsyncSession) -> ModerationUseCases:
    action_service = ModerationActionService(
        listings=FakeListingModerationCommandPort(),
        accounts=FakeAccountSuspensionCommandPort(),
        profiles=FakeProfileModerationCommandPort(),
    )
    return ModerationUseCases(
        cases=SqlalchemyModerationCaseRepository(session),
        action_service=action_service,
        outbox=OutboxWriter(session, OutboxEventRow),
    )


async def test_content_reported_redelivery_opens_the_case_exactly_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    listing_id = uuid4()
    reporter_id = uuid4()
    event = EventEnvelope(
        event_id=uuid4(),
        event_type="ContentReported",
        occurred_at=NOW,
        actor=reporter_id,
        aggregate_type="Listing",
        aggregate_id=listing_id,
        payload={
            "subjectType": "LISTING",
            "subjectId": str(listing_id),
            "reporterUserId": str(reporter_id),
            "reason": "spam content",
        },
    )

    for _ in range(2):
        async with session_factory() as session:
            await handle_content_reported(session, event, _use_cases(session))
            await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        case = await repo.get_open_or_in_review_for_subject(SubjectType.LISTING, listing_id)
        assert case is not None
        assert case.status is CaseStatus.OPEN
        assert case.origin.report_reason == "spam content"

        ledger_rows = (
            (
                await session.execute(
                    select(ProcessedEventRow).where(ProcessedEventRow.event_id == event.event_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(ledger_rows) == 1


async def test_listing_flagged_redelivery_opens_the_case_exactly_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    listing_id = uuid4()
    event = EventEnvelope(
        event_id=uuid4(),
        event_type="ListingFlagged",
        occurred_at=NOW,
        actor=None,
        aggregate_type="Listing",
        aggregate_id=listing_id,
        payload={"reason": "duplicate-detection"},
    )

    for _ in range(2):
        async with session_factory() as session:
            await handle_listing_flagged(session, event, _use_cases(session))
            await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyModerationCaseRepository(session)
        case = await repo.get_open_or_in_review_for_subject(SubjectType.LISTING, listing_id)
        assert case is not None
        assert case.origin.rule_key == "duplicate-detection"
        assert case.reporter_user_id is None

        ledger_rows = (
            (
                await session.execute(
                    select(ProcessedEventRow).where(ProcessedEventRow.event_id == event.event_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(ledger_rows) == 1
