"""Integration tests: `SqlalchemyListingRepository`/`SqlalchemyFavoriteRepository`/
`SqlalchemySubscriptionSnapshotRepository` round-trip against real PostgreSQL, including child
`ImageAttachment`/`LifecycleTransitionRecord` persistence, the `favorite` uniqueness constraint,
and optimistic-locking (`StaleDataError` on a lost update)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from catalog.application.ports import SubscriptionSnapshot
from catalog.domain.favorite import Favorite
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ImageStatus, ListingType
from catalog.infrastructure.persistence.repository import (
    SqlalchemyFavoriteRepository,
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from shared_kernel import BusinessProfileId, ListingId, UserId

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _new_listing(owner: UserId) -> Listing:
    return Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.PRODUCT,
        owner_user_id=owner,
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/x",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="Repo round-trip fixture",
        description="desc",
        attributes={"rooms": 2},
        price=None,
        location=None,
        slug="repo-round-trip-fixture",
        now=NOW,
    )


async def test_add_and_get_by_id_round_trips_with_images_and_transitions(
    db_session: AsyncSession,
) -> None:
    owner = UserId(value=uuid4())
    listing = _new_listing(owner)
    listing = listing.attach_image(image_id=uuid4(), media_asset_id=uuid4(), now=NOW)
    listing = listing.publish(
        record_id=uuid4(), actor_user_id=owner.value, expires_at=NOW + timedelta(days=30), now=NOW
    )

    repo = SqlalchemyListingRepository(db_session)
    await repo.add(listing)
    await db_session.flush()

    fetched = await repo.get_by_id(listing.id)
    assert fetched is not None
    assert fetched.title == listing.title
    assert len(fetched.images) == 1
    assert [t.transition_kind for t in fetched.transitions] == [
        t.transition_kind for t in listing.transitions
    ]


async def test_save_replaces_children_wholesale(db_session: AsyncSession) -> None:
    owner = UserId(value=uuid4())
    listing = _new_listing(owner)
    repo = SqlalchemyListingRepository(db_session)
    await repo.add(listing)
    await db_session.flush()

    media_asset_id = uuid4()
    updated = listing.attach_image(image_id=uuid4(), media_asset_id=media_asset_id, now=NOW)
    updated = updated.update_image_status(
        media_asset_id=media_asset_id, status=ImageStatus.CLEAN, now=NOW
    )
    saved = await repo.save(updated)

    refetched = await repo.get_by_id(listing.id)
    assert refetched is not None
    assert len(refetched.images) == 1
    assert refetched.images[0].status is ImageStatus.CLEAN
    assert saved.lock_version == refetched.lock_version


async def test_save_bumps_lock_version(db_session: AsyncSession) -> None:
    owner = UserId(value=uuid4())
    listing = _new_listing(owner)
    repo = SqlalchemyListingRepository(db_session)
    await repo.add(listing)
    await db_session.flush()

    saved = await repo.save(listing)
    assert saved.lock_version == listing.lock_version + 1


async def test_add_then_save_without_an_intervening_flush(db_session: AsyncSession) -> None:
    """DEF-15: `add()` followed directly by `save()` -- no flush in between.

    This is exactly what `createListing` with `publish: true` does: `ListingUseCases.
    create_listing` calls `listings.add(listing)` and then, when `publish` is set,
    `_do_publish()` -> `listings.save(listing)`, with nothing flushing between the two. Every
    such request failed with an unhandled `IntegrityError` (`duplicate key value violates unique
    constraint "pk_listing_transition"`), surfaced to the caller as `500 DEPENDENCY_DEGRADED`.

    Mechanism: sessions are built with `autoflush=False` (`backbone.persistence.engine.
    make_session_factory`), so `add()` leaving its transition rows pending meant `save()`'s
    `DELETE FROM listing_transition` matched nothing, its own `flush()` then inserted the pending
    CREATE row, and the re-add loop immediately inserted a *second* row with that same primary
    key.

    Every other test in this file happens to call `db_session.flush()` right after `repo.add()`,
    which is why the suite never caught it -- the tests compensated for the gap the production
    path does not.
    """
    owner = UserId(value=uuid4())
    listing = _new_listing(owner)
    repo = SqlalchemyListingRepository(db_session)

    await repo.add(listing)
    published = listing.publish(
        record_id=uuid4(), actor_user_id=owner.value, expires_at=NOW + timedelta(days=30), now=NOW
    )
    saved = await repo.save(published)

    assert saved.lifecycle_state is published.lifecycle_state

    refetched = await repo.get_by_id(listing.id)
    assert refetched is not None
    # Both transitions survive exactly once each: the CREATE recorded by `add()` and the PUBLISH
    # recorded by `save()`. A duplicate here would mean the audit history double-counts.
    assert [t.transition_kind for t in refetched.transitions] == [
        t.transition_kind for t in published.transitions
    ]
    assert len({t.id for t in refetched.transitions}) == len(refetched.transitions)


async def test_concurrent_save_raises_stale_data_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = UserId(value=uuid4())
    listing = _new_listing(owner)

    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        await session.commit()

    async with session_factory() as session_a, session_factory() as session_b:
        repo_a = SqlalchemyListingRepository(session_a)
        repo_b = SqlalchemyListingRepository(session_b)
        loaded_a = await repo_a.get_by_id(listing.id)
        loaded_b = await repo_b.get_by_id(listing.id)
        assert loaded_a is not None and loaded_b is not None

        await repo_a.save(loaded_a)
        await session_a.commit()

        with pytest.raises(StaleDataError):
            await repo_b.save(loaded_b)
            await session_b.commit()


async def test_get_by_image_media_asset_id_finds_the_owning_listing(
    db_session: AsyncSession,
) -> None:
    owner = UserId(value=uuid4())
    media_asset_id = uuid4()
    listing = _new_listing(owner).attach_image(
        image_id=uuid4(), media_asset_id=media_asset_id, now=NOW
    )
    repo = SqlalchemyListingRepository(db_session)
    await repo.add(listing)
    await db_session.flush()

    found = await repo.get_by_image_media_asset_id(media_asset_id)
    assert found is not None
    assert found.id == listing.id

    assert await repo.get_by_image_media_asset_id(uuid4()) is None


async def test_favorite_unique_constraint_prevents_duplicate_rows(db_session: AsyncSession) -> None:
    owner = UserId(value=uuid4())
    listing = _new_listing(owner)
    await SqlalchemyListingRepository(db_session).add(listing)
    await db_session.flush()

    user_id = UserId(value=uuid4())
    favorites = SqlalchemyFavoriteRepository(db_session)
    await favorites.add(
        Favorite.create(favorite_id=uuid4(), user_id=user_id, listing_id=listing.id, now=NOW)
    )
    await db_session.flush()

    count = await favorites.count_for_listing(listing.id)
    assert count == 1


async def test_subscription_snapshot_upsert_is_idempotent_on_owner_profile(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemySubscriptionSnapshotRepository(db_session)
    owner_profile_id = BusinessProfileId(value=uuid4())

    await repo.upsert(
        SubscriptionSnapshot(
            owner_profile_id=owner_profile_id,
            entitlement_id=uuid4(),
            product_definition_id=None,
            quota_document={"max_active_listings": 5},
            valid_until=None,
            source_event_id=uuid4(),
        )
    )
    await db_session.flush()

    new_entitlement_id = uuid4()
    await repo.upsert(
        SubscriptionSnapshot(
            owner_profile_id=owner_profile_id,
            entitlement_id=new_entitlement_id,
            product_definition_id=None,
            quota_document={"max_active_listings": 10},
            valid_until=None,
            source_event_id=uuid4(),
        )
    )
    await db_session.flush()

    snapshot = await repo.get_for_profile(owner_profile_id)
    assert snapshot is not None
    assert snapshot.entitlement_id == new_entitlement_id
    assert snapshot.quota_document["max_active_listings"] == 10
