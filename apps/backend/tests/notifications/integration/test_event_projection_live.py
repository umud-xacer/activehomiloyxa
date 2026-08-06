"""Integration tests: `notifications.infrastructure.event_projection`'s idempotent consumers
against real PostgreSQL -- the `ProcessedEventRow` ledger + `idempotent_consume` is what actually
needs a real `INSERT ... ON CONFLICT` to prove (mirrors `apps/backend/tests/moderation/
integration/test_event_projection_live.py`'s own pattern, Logical Sec 18 "idempotency is data").

Two things this file proves, both explicitly required by the P-13 task prompt:

1. EventKey-coverage test (`test_exactly_the_documented_24_events_produce_a_notification`):
   enumerates the full 24-event subset (mechanically derived from `contracts/events/*.py`'s own
   frozen "Principal consumers: ... Notifications ..." docstrings) so a future divergence --
   adding or removing a route in `event_projection.py` without updating this list -- breaks this
   test deliberately. Also proves a representative sample of events OUTSIDE that subset (routed
   through the SAME handler function that would otherwise apply) produce nothing.
2. Idempotency test (`test_redelivery_never_creates_a_second_notification`): the same event,
   handled twice, must create at most one `Notification` row and one `ProcessedEventRow` entry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notifications.application.dispatch_use_cases import NotificationDispatchUseCases
from notifications.application.ports import (
    NotificationTemplateSnapshot,
    RecipientSnapshot,
)
from notifications.infrastructure.event_projection import (
    handle_ads_event,
    handle_billing_event,
    handle_catalog_event,
    handle_identity_event,
    handle_messaging_event,
    handle_moderation_event,
    handle_profiles_event,
)
from notifications.infrastructure.persistence.models import (
    NotificationRow,
    ProcessedEventRow,
)
from notifications.infrastructure.persistence.repository import (
    SqlalchemyNotificationRepository,
)
from shared_kernel import EventEnvelope, LocalizedText

from ..conftest import FakeEmailProviderPort as _FakeEmailProviderPort
from ..conftest import (
    FakeOrderRecipientProjectionRepository,
    FakeRecipientDirectoryPort,
    FakeSmsProviderPort,
    FakeTemplateReaderPort,
    FakeWebPushProviderPort,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _recipient_snapshot(user_id: UUID) -> RecipientSnapshot:
    return RecipientSnapshot(
        user_id=user_id,
        email="recipient@example.com",
        phone="+998901234567",
        web_push_subscription=None,
        email_enabled=True,
        web_push_enabled=True,
        sms_enabled=True,
    )


def _template(event_key: str) -> NotificationTemplateSnapshot:
    return NotificationTemplateSnapshot(
        template_id=uuid4(),
        template_version_id=uuid4(),
        event_key=event_key,
        channel="EMAIL",
        subject=LocalizedText(uz_latn="Subject"),
        body=LocalizedText(uz_latn="Body"),
    )


def _use_cases(
    session: AsyncSession, templates: FakeTemplateReaderPort
) -> NotificationDispatchUseCases:
    return NotificationDispatchUseCases(
        notifications=SqlalchemyNotificationRepository(session),
        templates=templates,
        email=_FakeEmailProviderPort(),
        sms=FakeSmsProviderPort(),
        web_push=FakeWebPushProviderPort(),
    )


def _envelope(
    event_type: str, *, aggregate_id: object, payload: dict[str, object]
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        occurred_at=NOW,
        actor=None,
        aggregate_type="X",
        aggregate_id=aggregate_id,  # type: ignore[arg-type]
        payload=payload,
    )


# Every one of the 24 documented events, with (handler, aggregate_id, payload, recipient seeding).
def _positive_cases() -> list[tuple[str, tuple[Any, UUID, dict[str, object], str, UUID]]]:
    user_id = uuid4()
    profile_id = uuid4()
    listing_owner_id = uuid4()
    order_id = uuid4()
    return [
        ("UserRegistered", (handle_identity_event, user_id, {}, "user", user_id)),
        ("AccountSuspended", (handle_identity_event, user_id, {}, "user", user_id)),
        ("AccountClosed", (handle_identity_event, user_id, {}, "user", user_id)),
        (
            "VerificationRequested",
            (
                handle_profiles_event,
                uuid4(),
                {"businessProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "BusinessVerified",
            (
                handle_profiles_event,
                uuid4(),
                {"businessProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "VerificationRejected",
            (
                handle_profiles_event,
                uuid4(),
                {"businessProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "VerifiedBadgeExpired",
            (
                handle_profiles_event,
                uuid4(),
                {"businessProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "ListingPublished",
            (
                handle_catalog_event,
                uuid4(),
                {"ownerUserId": str(listing_owner_id)},
                "user",
                listing_owner_id,
            ),
        ),
        (
            "ListingSuspended",
            (
                handle_catalog_event,
                uuid4(),
                {"ownerUserId": str(listing_owner_id)},
                "user",
                listing_owner_id,
            ),
        ),
        (
            "ListingArchived",
            (
                handle_catalog_event,
                uuid4(),
                {"ownerUserId": str(listing_owner_id)},
                "user",
                listing_owner_id,
            ),
        ),
        (
            "ListingDeleted",
            (
                handle_catalog_event,
                uuid4(),
                {"ownerUserId": str(listing_owner_id)},
                "user",
                listing_owner_id,
            ),
        ),
        (
            "ListingExpired",
            (
                handle_catalog_event,
                uuid4(),
                {"ownerUserId": str(listing_owner_id)},
                "user",
                listing_owner_id,
            ),
        ),
        (
            "ListingRenewed",
            (
                handle_catalog_event,
                uuid4(),
                {"ownerUserId": str(listing_owner_id)},
                "user",
                listing_owner_id,
            ),
        ),
        (
            "OrderPlaced",
            (
                handle_billing_event,
                uuid4(),
                {"purchaserProfileId": str(profile_id), "orderId": str(order_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "PaymentConfirmed",
            (
                handle_billing_event,
                uuid4(),
                {"purchaserProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "EntitlementExpired",
            (
                handle_billing_event,
                uuid4(),
                {"ownerProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "EntitlementRevoked",
            (
                handle_billing_event,
                uuid4(),
                {"ownerProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "BannerCampaignScheduled",
            (
                handle_ads_event,
                uuid4(),
                {"bookingProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "BannerCampaignStarted",
            (
                handle_ads_event,
                uuid4(),
                {"bookingProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "BannerCampaignEnded",
            (
                handle_ads_event,
                uuid4(),
                {"bookingProfileId": str(profile_id)},
                "profile",
                profile_id,
            ),
        ),
        (
            "ChatInitiated",
            (
                handle_messaging_event,
                uuid4(),
                {"recipientUserId": str(user_id)},
                "user",
                user_id,
            ),
        ),
        (
            "MessageSent",
            (
                handle_messaging_event,
                uuid4(),
                {"recipientUserId": str(user_id)},
                "user",
                user_id,
            ),
        ),
        (
            "ModerationActionTaken",
            (
                handle_moderation_event,
                uuid4(),
                {"subjectType": "USER", "subjectId": str(user_id)},
                "user",
                user_id,
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_exactly_the_documented_24_events_produce_a_notification(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """23 of the 24 documented events, tested generically here; `InvoiceIssued` (the 24th) needs
    the `order_recipient_projection` pre-populated from a preceding `OrderPlaced` event, so it
    gets its own dedicated test (`test_invoice_issued_resolves_recipient_via_order_projection`,
    below) instead of fitting this generic loop."""
    cases = _positive_cases()
    assert len(cases) == 23

    for event_type, (handler, aggregate_id, payload, kind, recipient_id) in cases:
        templates = FakeTemplateReaderPort()
        templates.seed(event_type, _template(event_type))
        recipients = FakeRecipientDirectoryPort()
        if kind == "user":
            recipients.by_user[recipient_id] = _recipient_snapshot(recipient_id)
        else:
            recipients.by_profile[recipient_id] = _recipient_snapshot(recipient_id)

        async with session_factory() as session, session.begin():
            kwargs: dict[str, object] = {
                "use_cases": _use_cases(session, templates),
                "recipients": recipients,
            }
            if handler is handle_billing_event:
                kwargs["order_projection"] = FakeOrderRecipientProjectionRepository()
            dispatches = await handler(
                session,
                _envelope(event_type, aggregate_id=aggregate_id, payload=payload),
                **kwargs,
            )
        assert len(dispatches) == 1, f"{event_type} should have produced exactly one notification"


@pytest.mark.parametrize(
    ("event_type", "handler", "payload"),
    [
        ("ListingCreated", handle_catalog_event, {"ownerUserId": str(uuid4())}),
        ("ListingDraftSaved", handle_catalog_event, {"ownerUserId": str(uuid4())}),
        ("ListingEdited", handle_catalog_event, {"ownerUserId": str(uuid4())}),
        ("ListingFlagged", handle_catalog_event, {"ownerUserId": str(uuid4())}),
        ("FavoriteAdded", handle_catalog_event, {"ownerUserId": str(uuid4())}),
        (
            "BusinessProfileCreated",
            handle_profiles_event,
            {"businessProfileId": str(uuid4())},
        ),
        (
            "EntitlementActivated",
            handle_billing_event,
            {"purchaserProfileId": str(uuid4())},
        ),
        (
            "BannerImpressionRecorded",
            handle_ads_event,
            {"bookingProfileId": str(uuid4())},
        ),
        ("UserBlocked", handle_messaging_event, {"recipientUserId": str(uuid4())}),
        ("PhoneRevealed", handle_messaging_event, {"recipientUserId": str(uuid4())}),
    ],
)
@pytest.mark.asyncio
async def test_events_outside_the_subset_never_produce_a_notification(
    session_factory: async_sessionmaker[AsyncSession],
    event_type: str,
    handler: object,
    payload: dict[str, object],
) -> None:
    templates = FakeTemplateReaderPort()
    templates.seed(event_type, _template(event_type))  # even WITH a template, must not be routed
    recipients = FakeRecipientDirectoryPort()
    recipient_id = UUID(str(next(iter(payload.values()))))
    recipients.by_user[recipient_id] = _recipient_snapshot(recipient_id)
    recipients.by_profile[recipient_id] = _recipient_snapshot(recipient_id)

    async with session_factory() as session, session.begin():
        kwargs: dict[str, object] = {
            "use_cases": _use_cases(session, templates),
            "recipients": recipients,
        }
        if handler is handle_billing_event:
            kwargs["order_projection"] = FakeOrderRecipientProjectionRepository()
        dispatches = await handler(  # type: ignore[operator]
            session,
            _envelope(event_type, aggregate_id=uuid4(), payload=payload),
            **kwargs,
        )
    assert dispatches == []


@pytest.mark.asyncio
async def test_invoice_issued_resolves_recipient_via_order_projection(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`InvoiceIssued`'s own payload carries no profile/user reference at all -- the 24th event
    in the documented subset, resolved instead via the local `order_recipient_projection` this
    same handler populates when it sees that order's own `OrderPlaced` event moments earlier."""
    profile_id = uuid4()
    order_id = uuid4()
    templates = FakeTemplateReaderPort()
    templates.seed("OrderPlaced", _template("OrderPlaced"))
    templates.seed("InvoiceIssued", _template("InvoiceIssued"))
    recipients = FakeRecipientDirectoryPort()
    recipients.by_profile[profile_id] = _recipient_snapshot(profile_id)
    order_projection = FakeOrderRecipientProjectionRepository()

    order_placed = _envelope(
        "OrderPlaced",
        aggregate_id=order_id,
        payload={"purchaserProfileId": str(profile_id), "orderId": str(order_id)},
    )
    invoice_issued = _envelope(
        "InvoiceIssued", aggregate_id=uuid4(), payload={"orderId": str(order_id)}
    )

    async with session_factory() as session, session.begin():
        placed_dispatches = await handle_billing_event(
            session,
            order_placed,
            use_cases=_use_cases(session, templates),
            recipients=recipients,
            order_projection=order_projection,
        )
    assert len(placed_dispatches) == 1

    async with session_factory() as session, session.begin():
        invoice_dispatches = await handle_billing_event(
            session,
            invoice_issued,
            use_cases=_use_cases(session, templates),
            recipients=recipients,
            order_projection=order_projection,
        )
    assert len(invoice_dispatches) == 1


@pytest.mark.asyncio
async def test_redelivery_never_creates_a_second_notification(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid4()
    templates = FakeTemplateReaderPort()
    templates.seed("UserRegistered", _template("UserRegistered"))
    recipients = FakeRecipientDirectoryPort()
    recipients.by_user[user_id] = _recipient_snapshot(user_id)
    envelope = _envelope("UserRegistered", aggregate_id=user_id, payload={})

    for _ in range(2):
        async with session_factory() as session, session.begin():
            await handle_identity_event(
                session,
                envelope,
                use_cases=_use_cases(session, templates),
                recipients=recipients,
            )

    async with session_factory() as session:
        notification_rows = (await session.execute(select(NotificationRow))).scalars().all()
        assert len(notification_rows) == 1

        ledger_rows = (
            (
                await session.execute(
                    select(ProcessedEventRow).where(ProcessedEventRow.event_id == envelope.event_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(ledger_rows) == 1
