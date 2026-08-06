"""A second, structurally different idempotency proof, complementing `test_outbox_dispatcher_
redelivery_no_duplicate_side_effects.py` (a COUNTER-style handler, where "duplicate" means a
double-incremented value). `catalog.infrastructure.event_projection.handle_listing_promotion_
event` is a PROJECTION-SET-style handler: `ListingUseCases.apply_promotion_projection` sets the
listing's `promotion` field to a value AND republishes a fresh `ListingEdited` event every time
it runs (own docstring: "Applies `Listing.apply_promotion` and republishes `ListingEdited`") --
so redelivery's failure mode here isn't a wrong final VALUE (a second `apply_promotion` with the
same inputs converges to the same state), it's a DUPLICATE outbox event -- a second `ListingEdited`
row that every downstream consumer (search, notifications, ...) would then also have to process
again. Proves `idempotent_consume` (keyed on the triggering `EntitlementActivated`'s own
`event_id`) stops the redelivered call before it ever republishes that second event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from catalog.application import ListingUseCases
from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ListingType, PromotionKind
from catalog.infrastructure.event_projection import handle_listing_promotion_event
from catalog.infrastructure.persistence.base import CatalogBase
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.infrastructure.persistence.repository import (
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from shared_kernel import EventEnvelope, ListingId, UserId
from tests.integration.conftest import ensure_clean_schema

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _catalog_schema(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "catalog", CatalogBase)


class _UnusedCategoryFormPort:
    async def get_category(self, category_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def get_current_form_binding(self, category_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedPlatformSettingsReaderPort:
    async def get_catalog_settings(self) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedMediaAssetReaderPort:
    async def get_media_asset(self, media_asset_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")


def _use_cases(session: AsyncSession, listings: SqlalchemyListingRepository) -> ListingUseCases:
    return ListingUseCases(
        listings=listings,
        categories=_UnusedCategoryFormPort(),
        settings=_UnusedPlatformSettingsReaderPort(),
        media=_UnusedMediaAssetReaderPort(),
        outbox=OutboxWriter(session, CatalogOutboxEventRow),
        quota=QuotaEnforcementService(
            subscriptions=SqlalchemySubscriptionSnapshotRepository(session)
        ),
        duplicates=DuplicateDetectionService(listings=listings),
    )


async def test_redelivering_the_same_entitlement_activated_event_does_not_republish_listing_edited(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_id = UserId(value=uuid4())
    listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=owner_id,
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/x",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="A listing whose promotion event gets redelivered",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="a-listing-whose-promotion-event-gets-redelivered",
        now=NOW,
    ).publish(
        record_id=uuid4(),
        actor_user_id=owner_id.value,
        expires_at=NOW + timedelta(days=30),
        now=NOW,
    )

    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        await session.commit()

    entitlement_event_id = uuid4()
    envelope = EventEnvelope(
        event_id=entitlement_event_id,
        event_type="EntitlementActivated",
        occurred_at=NOW,
        actor=None,
        aggregate_type="Entitlement",
        aggregate_id=uuid4(),
        aggregate_version=1,
        payload={
            "listingId": str(listing.id.value),
            "entitlementType": "LISTING_PROMOTION",
            "kind": PromotionKind.PREMIUM.value,
            "validUntil": (NOW + timedelta(days=7)).isoformat(),
            "entitlementId": str(uuid4()),
        },
    )

    for _ in range(2):
        async with session_factory() as session, session.begin():
            listings_repo = SqlalchemyListingRepository(session)
            await handle_listing_promotion_event(
                session, envelope, _use_cases(session, listings_repo)
            )

    async with session_factory() as session:
        edited_rows = (
            (
                await session.execute(
                    select(CatalogOutboxEventRow).where(
                        CatalogOutboxEventRow.event_type == "ListingEdited"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(edited_rows) == 1, (
            "redelivery of the SAME EntitlementActivated must not republish a second "
            "ListingEdited -- every downstream consumer would otherwise reprocess it twice"
        )

        reloaded = await SqlalchemyListingRepository(session).get_by_id(listing.id)
        assert reloaded is not None
        assert reloaded.promotion is not None
        assert reloaded.promotion.kind is PromotionKind.PREMIUM
