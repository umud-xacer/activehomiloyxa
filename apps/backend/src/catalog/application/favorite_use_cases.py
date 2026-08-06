"""catalog/application -- `FavoriteUseCases` (Task P-07, FR-USER-004). The `Favorite` aggregate's
own use cases -- deliberately not folded into `ListingUseCases` (DDD Sec 5.3: "Separate from
Listing so favoriting never contends with listing writes"; a separate repository/unit of work,
Clean Architecture rule 2)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from catalog.application.exceptions import FavoriteNotFoundError, ListingNotFoundError
from catalog.application.ports import FavoriteRepository, ListingRepository
from catalog.domain.favorite import Favorite
from contracts.events.catalog import FavoriteAdded, FavoriteRemoved
from shared_kernel import ListingId, OutboxPort, UserId


class FavoriteUseCases:
    def __init__(
        self, *, favorites: FavoriteRepository, listings: ListingRepository, outbox: OutboxPort
    ) -> None:
        self._favorites = favorites
        self._listings = listings
        self._outbox = outbox

    async def add_favorite(
        self, *, user_id: UserId, listing_id: ListingId, now: datetime
    ) -> Favorite:
        """Idempotent: favoriting an already-favorited listing returns the existing row rather
        than raising or duplicating (Physical DB `UNIQUE(user_id, listing_id)` -- there is no
        partial state a second call could usefully change)."""
        existing = await self._favorites.get(user_id=user_id, listing_id=listing_id)
        if existing is not None:
            return existing
        if await self._listings.get_by_id(listing_id) is None:
            raise ListingNotFoundError(listing_id)
        favorite = Favorite.create(
            favorite_id=uuid4(), user_id=user_id, listing_id=listing_id, now=now
        )
        await self._favorites.add(favorite)
        event = FavoriteAdded(
            event_id=uuid4(),
            occurred_at=now,
            actor=user_id.value,
            aggregate_type="Favorite",
            aggregate_id=favorite.id,
            payload={"userId": str(user_id.value), "listingId": str(listing_id.value)},
        )
        await self._outbox.append(event)
        return favorite

    async def remove_favorite(
        self, *, user_id: UserId, listing_id: ListingId, now: datetime
    ) -> None:
        existing = await self._favorites.get(user_id=user_id, listing_id=listing_id)
        if existing is None:
            raise FavoriteNotFoundError(listing_id.value)
        await self._favorites.delete(user_id=user_id, listing_id=listing_id)
        event = FavoriteRemoved(
            event_id=uuid4(),
            occurred_at=now,
            actor=user_id.value,
            aggregate_type="Favorite",
            aggregate_id=existing.id,
            payload={"userId": str(user_id.value), "listingId": str(listing_id.value)},
        )
        await self._outbox.append(event)

    async def list_favorites(
        self, *, user_id: UserId, cursor: str | None, limit: int
    ) -> tuple[list[Favorite], str | None]:
        return await self._favorites.list_for_user(user_id, cursor=cursor, limit=limit)

    async def count_for_listing(self, listing_id: ListingId) -> int:
        """Backs `getListingStatistics`'s `favorites` count (catalog's own data)."""
        return await self._favorites.count_for_listing(listing_id)
