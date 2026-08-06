"""analytics/infrastructure -- idempotent event consumers, one handler function per emitting
module (mirrors `notifications`/`ads`'s own established pattern). Each wraps `idempotent_consume`
keyed on `source_event_id` (the triggering `EventEnvelope.event_id`) under its own distinct
handler name, so redelivery of the same event is a no-op (I-22/I-23 exactly-once).

No handler ever calls back into the emitting module to enrich a fact -- every field stored here
comes from `envelope.payload` alone (Absolute Architecture Rule 1: analytics imports
`shared_kernel` only).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analytics.application.audit_use_cases import AuditUseCases
from analytics.application.metric_use_cases import MetricUseCases
from analytics.infrastructure.persistence.models import ProcessedEventRow
from backbone.idempotency import idempotent_consume
from shared_kernel import EventEnvelope, ListingId, UserId

# BC-11 (moderation) -- Audit only (DDD Sec 6: "ModerationActionTaken ... Audit, Notifications").
_MODERATION_ACTIONS = {"ModerationActionTaken"}

# BC-04 (configuration) -- Audit only, the nine ConfigurationChanged specialisations actually
# published (configuration.domain.events.resolve_configuration_changed_event_type's own literal
# set; "ConfigurationChanged" itself is never the published event_type).
_CONFIGURATION_ACTIONS = {
    "CategoryCreated",
    "CategoryChanged",
    "CategoryRetired",
    "FormDefinitionPublished",
    "ProductDefinitionChanged",
    "PlacementSlotDefined",
    "RoleDefinitionChanged",
    "SearchConfigurationChanged",
    "NotificationTemplateChanged",
    "PlatformSettingsChanged",
}

# BC-08 (billing) -- Audit only (DDD Sec 6: "PaymentConfirmed ... Audit, Notifications"). Other
# billing events (OrderPlaced, InvoiceIssued, Entitlement*) are not administrative actions under
# I-22's own scope and are not consumed here.
_BILLING_ACTIONS = {"PaymentConfirmed"}

# BC-01 (identity) -- Audit only (DDD Sec 6: "AccountSuspended / AccountClosed ... Audit").
# UserRegistered is deliberately NOT consumed here -- it is neither an administrative action
# (I-22) nor a closed-vocabulary metric (I-23); see report_use_cases.py's USER_GROWTH gap note.
_IDENTITY_ACTIONS = {"AccountSuspended", "AccountClosed"}

# BC-02 (profiles) -- Audit only (DDD Sec 6: "BusinessVerified ... Analytics, Audit";
# "VerificationRejected ... Notifications, Audit"). VerificationRequested is the submission side
# (a self-service profile-owner action, not administrative) and is not consumed here.
_PROFILES_ACTIONS = {"BusinessVerified", "VerificationRejected"}

# BC-03 (catalog) -- MetricEvent only.
_CATALOG_METRIC_KEYS = {
    "ListingViewed": "LISTING_VIEWED",
    "ContactButtonClicked": "CONTACT_BUTTON_CLICKED",
    "FavoriteAdded": "FAVORITE_ADDED",
    "PremiumListingStat": "PREMIUM_LISTING_STAT",
}

# BC-07 (messaging) -- MetricEvent only.
_MESSAGING_METRIC_KEYS = {
    "PhoneRevealed": "PHONE_REVEALED",
    "ChatInitiated": "CHAT_INITIATED",
}

# BC-09 (ads) -- MetricEvent only.
_ADS_METRIC_KEYS = {
    "BannerImpressionRecorded": "BANNER_IMPRESSION_RECORDED",
    "BannerClickRecorded": "BANNER_CLICK_RECORDED",
}


def _actor_user_id(envelope: EventEnvelope) -> UserId | None:
    return UserId(value=envelope.actor) if envelope.actor is not None else None


async def _record_audit_fact(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    handler: str,
    audit_use_cases: AuditUseCases,
    target_type: str | None,
    target_id: UUID | None,
) -> None:
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=handler
    ) as is_fresh:
        if not is_fresh:
            return
        await audit_use_cases.record_audit_fact(
            action=envelope.event_type,
            actor_user_id=_actor_user_id(envelope),
            actor_context=None,
            target_type=target_type,
            target_id=target_id,
            payload=envelope.payload,
            source_event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )


async def handle_moderation_event(
    session: AsyncSession, envelope: EventEnvelope, *, audit_use_cases: AuditUseCases
) -> None:
    if envelope.event_type not in _MODERATION_ACTIONS:
        return
    subject_id = envelope.payload.get("subjectId")
    await _record_audit_fact(
        session,
        envelope,
        handler="analytics.handle_moderation_event",
        audit_use_cases=audit_use_cases,
        target_type=envelope.payload.get("subjectType"),
        target_id=UUID(subject_id) if subject_id else None,
    )


async def handle_configuration_event(
    session: AsyncSession, envelope: EventEnvelope, *, audit_use_cases: AuditUseCases
) -> None:
    if envelope.event_type not in _CONFIGURATION_ACTIONS:
        return
    await _record_audit_fact(
        session,
        envelope,
        handler="analytics.handle_configuration_event",
        audit_use_cases=audit_use_cases,
        target_type=envelope.payload.get("entityType"),
        target_id=envelope.aggregate_id if isinstance(envelope.aggregate_id, UUID) else None,
    )


async def handle_billing_event(
    session: AsyncSession, envelope: EventEnvelope, *, audit_use_cases: AuditUseCases
) -> None:
    if envelope.event_type not in _BILLING_ACTIONS:
        return
    invoice_id = envelope.payload.get("invoiceId")
    await _record_audit_fact(
        session,
        envelope,
        handler="analytics.handle_billing_event",
        audit_use_cases=audit_use_cases,
        target_type="Invoice",
        target_id=UUID(invoice_id) if invoice_id else None,
    )


async def handle_identity_event(
    session: AsyncSession, envelope: EventEnvelope, *, audit_use_cases: AuditUseCases
) -> None:
    if envelope.event_type not in _IDENTITY_ACTIONS:
        return
    account_id = envelope.payload.get("accountId")
    await _record_audit_fact(
        session,
        envelope,
        handler="analytics.handle_identity_event",
        audit_use_cases=audit_use_cases,
        target_type="UserAccount",
        target_id=UUID(account_id) if account_id else None,
    )


async def handle_profiles_event(
    session: AsyncSession, envelope: EventEnvelope, *, audit_use_cases: AuditUseCases
) -> None:
    if envelope.event_type not in _PROFILES_ACTIONS:
        return
    case_id = envelope.payload.get("verificationCaseId")
    await _record_audit_fact(
        session,
        envelope,
        handler="analytics.handle_profiles_event",
        audit_use_cases=audit_use_cases,
        target_type="VerificationCase",
        target_id=UUID(case_id) if case_id else None,
    )


async def handle_catalog_event(
    session: AsyncSession, envelope: EventEnvelope, *, metric_use_cases: MetricUseCases
) -> None:
    metric_key = _CATALOG_METRIC_KEYS.get(envelope.event_type)
    if metric_key is None:
        return
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler="analytics.handle_catalog_event",
    ) as is_fresh:
        if not is_fresh:
            return
        listing_id = envelope.payload.get("listingId")
        user_id = envelope.payload.get("userId") or envelope.payload.get("viewerUserId")
        await metric_use_cases.record_metric(
            metric_key=metric_key,
            listing_id=ListingId(value=UUID(listing_id)) if listing_id else None,
            user_id=UserId(value=UUID(user_id)) if user_id else None,
            campaign_id=None,
            payload=envelope.payload,
            source_event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )


async def handle_messaging_event(
    session: AsyncSession, envelope: EventEnvelope, *, metric_use_cases: MetricUseCases
) -> None:
    metric_key = _MESSAGING_METRIC_KEYS.get(envelope.event_type)
    if metric_key is None:
        return
    async with idempotent_consume(
        session,
        ProcessedEventRow,
        event_id=envelope.event_id,
        handler="analytics.handle_messaging_event",
    ) as is_fresh:
        if not is_fresh:
            return
        # `PhoneRevealed`'s existing payload carries no `listingId` (only `conversationId`/
        # `revealerUserId`/`revealedUserId`) -- the fact is still captured (I-23), but with
        # `listing_id=None`, so it never updates a per-listing counter (README "Known gaps").
        listing_id = envelope.payload.get("listingId")
        user_id = envelope.payload.get("initiatorUserId") or envelope.payload.get("revealerUserId")
        await metric_use_cases.record_metric(
            metric_key=metric_key,
            listing_id=ListingId(value=UUID(listing_id)) if listing_id else None,
            user_id=UserId(value=UUID(user_id)) if user_id else None,
            campaign_id=None,
            payload=envelope.payload,
            source_event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )


async def handle_ads_event(
    session: AsyncSession, envelope: EventEnvelope, *, metric_use_cases: MetricUseCases
) -> None:
    metric_key = _ADS_METRIC_KEYS.get(envelope.event_type)
    if metric_key is None:
        return
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler="analytics.handle_ads_event"
    ) as is_fresh:
        if not is_fresh:
            return
        campaign_id = envelope.payload.get("campaignId")
        await metric_use_cases.record_metric(
            metric_key=metric_key,
            listing_id=None,
            user_id=None,
            campaign_id=UUID(campaign_id) if campaign_id else None,
            payload=envelope.payload,
            source_event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
        )
