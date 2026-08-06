"""Integration tests: `messaging.infrastructure.event_projection.handle_listing_created` against
real PostgreSQL -- the `ProcessedEventRow` ledger + `idempotent_consume` needs a real
`INSERT ... ON CONFLICT` to prove, mirroring `apps/backend/tests/catalog/integration/
test_event_projection_live.py`'s own pattern (Logical Sec 18 "idempotency is data")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from messaging.infrastructure.event_projection import handle_listing_created
from messaging.infrastructure.persistence.repository import SqlalchemyListingOwnerProjectionReader
from shared_kernel import EventEnvelope

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _listing_created_envelope(*, listing_id, owner_user_id) -> EventEnvelope:  # type: ignore[no-untyped-def]
    return EventEnvelope(
        event_id=uuid4(),
        event_type="ListingCreated",
        occurred_at=NOW,
        actor=owner_user_id,
        aggregate_type="Listing",
        aggregate_id=listing_id,
        payload={"listingId": str(listing_id), "ownerUserId": str(owner_user_id)},
    )


async def test_projects_the_owner_on_first_delivery(db_session: AsyncSession) -> None:
    listing_id = uuid4()
    owner_id = uuid4()
    envelope = _listing_created_envelope(listing_id=listing_id, owner_user_id=owner_id)

    await handle_listing_created(db_session, envelope)
    await db_session.commit()

    reader = SqlalchemyListingOwnerProjectionReader(db_session)
    owner = await reader.get_owner(listing_id)
    assert owner is not None
    assert owner.value == owner_id


async def test_redelivery_of_the_same_event_is_a_no_op(db_session: AsyncSession) -> None:
    listing_id = uuid4()
    owner_id = uuid4()
    envelope = _listing_created_envelope(listing_id=listing_id, owner_user_id=owner_id)

    await handle_listing_created(db_session, envelope)
    await db_session.commit()
    # redeliver the SAME event_id -- idempotent_consume must treat this as already-applied.
    await handle_listing_created(db_session, envelope)
    await db_session.commit()

    reader = SqlalchemyListingOwnerProjectionReader(db_session)
    owner = await reader.get_owner(listing_id)
    assert owner is not None
    assert owner.value == owner_id


async def test_malformed_payload_is_ignored_not_raised(db_session: AsyncSession) -> None:
    envelope = EventEnvelope(
        event_id=uuid4(),
        event_type="ListingCreated",
        occurred_at=NOW,
        actor=None,
        aggregate_type="Listing",
        aggregate_id=uuid4(),
        payload={},
    )
    await handle_listing_created(db_session, envelope)
    await db_session.commit()
