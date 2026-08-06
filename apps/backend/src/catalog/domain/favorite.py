"""catalog -- the `Favorite` aggregate (DDD Sec 5.3 `AR: Favorite [P]`: "Minimal root: UserId +
ListingId + timestamp. Separate from Listing so favoriting never contends with listing writes").
A distinct aggregate root, its own repository, its own unit of work -- the canonical
association-aggregate resolution of a many-to-many (FR-USER-004), not a child collection on
either `Listing` or a `UserAccount` catalog does not own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared_kernel import ListingId, UserId


@dataclass(frozen=True)
class Favorite:
    """Unique on `(user_id, listing_id)` (Physical DB `UNIQUE(user_id, listing_id)`) -- enforced
    by the repository/database, not re-derived here (a favorite either exists or it doesn't;
    there is no partial state to guard with a domain method)."""

    id: UUID
    user_id: UserId
    listing_id: ListingId
    created_at: datetime

    @staticmethod
    def create(
        *, favorite_id: UUID, user_id: UserId, listing_id: ListingId, now: datetime
    ) -> Favorite:
        return Favorite(id=favorite_id, user_id=user_id, listing_id=listing_id, created_at=now)
