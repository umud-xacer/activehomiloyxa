"""Idempotent projection handlers for the two event streams moderation consumes but never
imports the producer of (SAD Sec 8.1: moderation may statically import `shared_kernel` only):
messaging's real `ContentReported` (Task P-10, already published by `messaging.application.
report_use_cases.ReportUseCases.create_report`) and catalog's real `ListingFlagged` (Task P-07,
already published by `catalog.application.listing_use_cases.ListingUseCases`'s own
duplicate-detection flow). Both handlers wrap `backbone.idempotency.consumer.idempotent_consume`
against moderation's own `ProcessedEventRow` ledger, keyed on the *producing* event's own
`event_id` -- redelivery of the same event is a no-op, never a duplicate case.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from backbone.idempotency import idempotent_consume
from moderation.application import ModerationUseCases
from moderation.domain import SubjectType
from moderation.infrastructure.persistence import ProcessedEventRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from shared_kernel import EventEnvelope

_REPORT_HANDLER = "moderation.content_reported_projection"
_FLAG_HANDLER = "moderation.listing_flagged_projection"

_SUBJECT_TYPE_BY_WIRE_VALUE = {
    "LISTING": SubjectType.LISTING,
    "CONVERSATION": SubjectType.CONVERSATION,
    "USER": SubjectType.USER,
    "PROFILE": SubjectType.PROFILE,
}


async def handle_content_reported(
    session: AsyncSession, envelope: EventEnvelope, use_cases: ModerationUseCases
) -> None:
    """FR-MOD-001/FR-MSG-005: opens/attaches a `ModerationCase` from messaging's real
    `ContentReported` event (`messaging.application.report_use_cases.ReportUseCases.create_report`
    payload: `subjectType`/`subjectId`/`reporterUserId`/`reason`)."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_REPORT_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        if envelope.event_type != "ContentReported":
            return
        payload = envelope.payload
        subject_type_raw = payload.get("subjectType")
        subject_id_raw = payload.get("subjectId")
        reporter_user_id_raw = payload.get("reporterUserId")
        reason = payload.get("reason")
        if subject_type_raw is None or subject_id_raw is None or reporter_user_id_raw is None:
            return
        subject_type = _SUBJECT_TYPE_BY_WIRE_VALUE.get(str(subject_type_raw))
        if subject_type is None:
            return
        await use_cases.submit_report(
            subject_type=subject_type,
            subject_id=UUID(str(subject_id_raw)),
            reporter_user_id=UUID(str(reporter_user_id_raw)),
            reason=str(reason) if reason else "(no reason given)",
            now=envelope.occurred_at,
        )


async def handle_listing_flagged(
    session: AsyncSession, envelope: EventEnvelope, use_cases: ModerationUseCases
) -> None:
    """FR-MOD-002: opens/attaches a `ModerationCase` from catalog's real `ListingFlagged` event.
    The FlaggingService (DDD Sec 5.11) is reactive-only here -- see `moderation_use_cases.
    ModerationUseCases.auto_flag`'s own docstring for why the rule evaluation itself cannot live
    inside moderation."""
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_FLAG_HANDLER
    ) as is_fresh:
        if not is_fresh:
            return
        if envelope.event_type != "ListingFlagged":
            return
        listing_id = str(envelope.aggregate_id)
        rule_key = envelope.payload.get("reason") or "unspecified-rule"
        await use_cases.auto_flag(
            subject_type=SubjectType.LISTING,
            subject_id=UUID(listing_id),
            rule_key=str(rule_key),
            now=envelope.occurred_at,
        )
