"""`catalog.domain.favorite.Favorite` -- a minimal aggregate root, DDD Sec 5.3 (FR-USER-004)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from catalog.domain.favorite import Favorite
from shared_kernel import ListingId, UserId

NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def test_create_stamps_user_listing_and_timestamp() -> None:
    user_id = UserId(value=uuid4())
    listing_id = ListingId(value=uuid4())
    favorite_id = uuid4()

    favorite = Favorite.create(
        favorite_id=favorite_id, user_id=user_id, listing_id=listing_id, now=NOW
    )

    assert favorite.id == favorite_id
    assert favorite.user_id == user_id
    assert favorite.listing_id == listing_id
    assert favorite.created_at == NOW


def test_favorite_is_immutable() -> None:
    favorite = Favorite.create(
        favorite_id=uuid4(),
        user_id=UserId(value=uuid4()),
        listing_id=ListingId(value=uuid4()),
        now=NOW,
    )
    import dataclasses

    assert dataclasses.is_dataclass(favorite)
    assert favorite.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
