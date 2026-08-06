"""catalog/application -- `DuplicateDetectionService` (FR-ADV-009). "Flags likely duplicates per
configurable rules" -- no literal matching algorithm is specified in any approved document (the
same class of documentation gap as identity's P-05 OTP-throttle constants, resolved there as an
implementation-chosen constant); this task's own minimal, defensible heuristic is scoped
"same owner + same category" (a repository query, `ListingRepository.find_recent_by_owner_
category`) narrowed to an exact match on the normalised title comparator
(`catalog.domain.policies.normalize_title_for_duplicate_matching`, the pure half of this rule).
A flagged listing is held for moderation (BRULE-17/DEC-14): `ListingUseCases` calls
`Listing.flag()` when this service reports a hit, before publish is honoured."""

from __future__ import annotations

from uuid import UUID

from catalog.application.ports import ListingRepository
from catalog.domain.listing import Listing
from catalog.domain.policies import normalize_title_for_duplicate_matching
from shared_kernel import ListingId, UserId

_CANDIDATE_SCAN_LIMIT = 25
"""Bounded scan window -- this is a cheap heuristic, not a search-grade comparison
(BC-05/search indexing is out of this task's scope)."""


class DuplicateDetectionService:
    def __init__(self, *, listings: ListingRepository) -> None:
        self._listings = listings

    async def is_likely_duplicate(
        self,
        *,
        owner_user_id: UserId,
        category_id: UUID,
        title: str,
        exclude_listing_id: ListingId | None = None,
    ) -> bool:
        candidates: list[Listing] = await self._listings.find_recent_by_owner_category(
            owner_user_id=owner_user_id,
            category_id=category_id,
            exclude_listing_id=exclude_listing_id,
            limit=_CANDIDATE_SCAN_LIMIT,
        )
        normalized = normalize_title_for_duplicate_matching(title)
        return any(
            normalize_title_for_duplicate_matching(candidate.title) == normalized
            for candidate in candidates
            if candidate.lifecycle_state.value != "DELETED"
        )
