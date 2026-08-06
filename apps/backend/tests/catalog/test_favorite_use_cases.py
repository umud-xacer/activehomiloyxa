"""`catalog.application.FavoriteUseCases` (FR-USER-004) -- the `Favorite` aggregate's own use
cases, deliberately separate from `ListingUseCases` (DDD Sec 5.3: "Separate from Listing so
favoriting never contends with listing writes")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from catalog.application.exceptions import FavoriteNotFoundError, ListingNotFoundError
from catalog.application.favorite_use_cases import FavoriteUseCases
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ListingType
from shared_kernel import ListingId, UserId

from .conftest import FakeFavoriteRepository, FakeListingRepository, FakeOutbox

NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def favorite_use_cases(
    fake_favorites: FakeFavoriteRepository,
    fake_listings: FakeListingRepository,
    fake_outbox: FakeOutbox,
) -> FavoriteUseCases:
    return FavoriteUseCases(favorites=fake_favorites, listings=fake_listings, outbox=fake_outbox)


async def _seed_listing(fake_listings: FakeListingRepository) -> Listing:
    listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=UserId(value=uuid4()),
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
    )
    await fake_listings.add(listing)
    return listing


async def test_add_favorite_then_it_is_listed(
    favorite_use_cases: FavoriteUseCases,
    fake_listings: FakeListingRepository,
    fake_outbox: FakeOutbox,
) -> None:
    listing = await _seed_listing(fake_listings)
    user_id = UserId(value=uuid4())

    favorite = await favorite_use_cases.add_favorite(
        user_id=user_id, listing_id=listing.id, now=NOW
    )
    assert favorite.listing_id == listing.id

    items, _cursor = await favorite_use_cases.list_favorites(user_id=user_id, cursor=None, limit=20)
    assert [f.listing_id for f in items] == [listing.id]
    assert [e.event_type for e in fake_outbox.events] == ["FavoriteAdded"]


async def test_add_favorite_is_idempotent(
    favorite_use_cases: FavoriteUseCases,
    fake_listings: FakeListingRepository,
    fake_outbox: FakeOutbox,
) -> None:
    listing = await _seed_listing(fake_listings)
    user_id = UserId(value=uuid4())

    first = await favorite_use_cases.add_favorite(user_id=user_id, listing_id=listing.id, now=NOW)
    second = await favorite_use_cases.add_favorite(user_id=user_id, listing_id=listing.id, now=NOW)

    assert first.id == second.id
    assert [e.event_type for e in fake_outbox.events] == ["FavoriteAdded"]  # only once


async def test_add_favorite_unknown_listing_raises(favorite_use_cases: FavoriteUseCases) -> None:
    with pytest.raises(ListingNotFoundError):
        await favorite_use_cases.add_favorite(
            user_id=UserId(value=uuid4()), listing_id=ListingId(value=uuid4()), now=NOW
        )


async def test_remove_favorite(
    favorite_use_cases: FavoriteUseCases,
    fake_listings: FakeListingRepository,
    fake_outbox: FakeOutbox,
) -> None:
    listing = await _seed_listing(fake_listings)
    user_id = UserId(value=uuid4())
    await favorite_use_cases.add_favorite(user_id=user_id, listing_id=listing.id, now=NOW)

    await favorite_use_cases.remove_favorite(user_id=user_id, listing_id=listing.id, now=NOW)

    items, _cursor = await favorite_use_cases.list_favorites(user_id=user_id, cursor=None, limit=20)
    assert items == []
    assert [e.event_type for e in fake_outbox.events] == ["FavoriteAdded", "FavoriteRemoved"]


async def test_remove_favorite_never_favorited_raises(
    favorite_use_cases: FavoriteUseCases, fake_listings: FakeListingRepository
) -> None:
    listing = await _seed_listing(fake_listings)
    with pytest.raises(FavoriteNotFoundError):
        await favorite_use_cases.remove_favorite(
            user_id=UserId(value=uuid4()), listing_id=listing.id, now=NOW
        )


async def test_count_for_listing(
    favorite_use_cases: FavoriteUseCases, fake_listings: FakeListingRepository
) -> None:
    listing = await _seed_listing(fake_listings)
    await favorite_use_cases.add_favorite(
        user_id=UserId(value=uuid4()), listing_id=listing.id, now=NOW
    )
    await favorite_use_cases.add_favorite(
        user_id=UserId(value=uuid4()), listing_id=listing.id, now=NOW
    )

    count = await favorite_use_cases.count_for_listing(listing.id)
    assert count == 2
