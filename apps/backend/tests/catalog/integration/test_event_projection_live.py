"""Integration tests: `catalog.infrastructure.event_projection`'s idempotent consumers against
real PostgreSQL -- the `ProcessedEventRow` ledger + `idempotent_consume` is what actually needs a
real `INSERT ... ON CONFLICT` to prove, mirroring `apps/backend/tests/backbone/integration/
test_dispatcher_idempotency.py`'s own pattern (Logical Sec 18 "idempotency is data")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.listing import Listing
from catalog.domain.value_objects import ListingType
from catalog.infrastructure.event_projection import handle_entitlement_event, handle_media_event
from catalog.infrastructure.persistence.models import ProcessedEventRow
from catalog.infrastructure.persistence.repository import (
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from shared_kernel import BusinessProfileId, EventEnvelope, ListingId, UserId

NOW = datetime(2026, 7, 11, tzinfo=UTC)


async def _seeded_listing_with_image(
    session_factory: async_sessionmaker[AsyncSession], media_asset_id: UUID
) -> Listing:
    owner = UserId(value=uuid4())
    listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=owner,
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/x",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="x",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="x",
        now=NOW,
    ).attach_image(image_id=uuid4(), media_asset_id=media_asset_id, now=NOW)
    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        await session.commit()
    return listing


async def test_media_event_redelivery_applies_the_projection_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    media_asset_id = uuid4()
    listing = await _seeded_listing_with_image(session_factory, media_asset_id)

    event = EventEnvelope(
        event_id=uuid4(),
        event_type="MediaAssetReady",
        occurred_at=NOW,
        actor=None,
        aggregate_type="MediaAsset",
        aggregate_id=media_asset_id,
        payload={"mediaAssetId": str(media_asset_id)},
    )

    for _ in range(2):
        async with session_factory() as session:
            await handle_media_event(session, event)
            await session.commit()

    async with session_factory() as session:
        reloaded = await SqlalchemyListingRepository(session).get_by_id(listing.id)
        assert reloaded is not None
        assert reloaded.images[0].status.value == "CLEAN"

        ledger_rows = (await session.execute(select(ProcessedEventRow))).scalars().all()
        assert len(ledger_rows) == 1
        assert ledger_rows[0].event_id == event.event_id


async def test_entitlement_event_redelivery_upserts_the_snapshot_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_profile_id = BusinessProfileId(value=uuid4())
    event = EventEnvelope(
        event_id=uuid4(),
        event_type="EntitlementIssued",
        occurred_at=NOW,
        actor=None,
        aggregate_type="Entitlement",
        aggregate_id=uuid4(),
        payload={
            "ownerProfileId": str(owner_profile_id.value),
            "entitlementId": str(uuid4()),
            "quota": {"max_active_listings": 5},
        },
    )

    for _ in range(2):
        async with session_factory() as session:
            await handle_entitlement_event(session, event)
            await session.commit()

    async with session_factory() as session:
        snapshot = await SqlalchemySubscriptionSnapshotRepository(session).get_for_profile(
            owner_profile_id
        )
        assert snapshot is not None
        assert snapshot.quota_document["max_active_listings"] == 5

        ledger_rows = (await session.execute(select(ProcessedEventRow))).scalars().all()
        assert len(ledger_rows) == 1
