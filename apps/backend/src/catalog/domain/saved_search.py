"""catalog -- the `SavedSearch` aggregate. A per-account bookmark of search criteria (the
`/properties` query params, opaque to this module) so the caller can re-run it later. Modelled on
`Favorite` (same module, same shape of problem: a minimal root of UserId + payload + timestamp,
its own repository so bookmarking never contends with listing writes) -- not a child collection on
a `UserAccount` catalog does not own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from shared_kernel import UserId


@dataclass(frozen=True)
class SavedSearch:
    """No uniqueness constraint on `(user_id, criteria)` -- unlike `Favorite`'s
    `(user_id, listing_id)`, a caller may save the same criteria twice under different names, or
    the same name is not guarded against duplication either; `name` is a free-text label the
    caller chose, not an identifier."""

    id: UUID
    user_id: UserId
    name: str
    criteria: dict[str, Any]
    created_at: datetime

    @staticmethod
    def create(
        *,
        saved_search_id: UUID,
        user_id: UserId,
        name: str,
        criteria: dict[str, Any],
        now: datetime,
    ) -> SavedSearch:
        return SavedSearch(
            id=saved_search_id, user_id=user_id, name=name, criteria=criteria, created_at=now
        )
