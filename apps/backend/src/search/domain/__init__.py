"""search/domain -- the `ListingSearchDocument` projection, the cross-script normalizer, the
ranking/capping policy, value objects, and the query model (Task P-08). Imports `shared_kernel`
only (Clean Architecture rule 1); never imported by another module (`domain/` is never part of a
module's public surface, AIR-02)."""

from __future__ import annotations

from search.domain.cross_script import normalize_for_matching, to_cyrillic, to_latin
from search.domain.exceptions import InvalidPromotionCapError, SearchDomainError
from search.domain.query import GeoFilter, SearchQuery
from search.domain.ranking import RankedCandidate, apply_promotion_cap
from search.domain.search_document import ListingSearchDocument
from search.domain.value_objects import (
    ListingType,
    PromotionKind,
    PromotionMarker,
    SortOption,
    SuggestionType,
)

__all__ = [
    "GeoFilter",
    "InvalidPromotionCapError",
    "ListingSearchDocument",
    "ListingType",
    "PromotionKind",
    "PromotionMarker",
    "RankedCandidate",
    "SearchDomainError",
    "SearchQuery",
    "SortOption",
    "SuggestionType",
    "apply_promotion_cap",
    "normalize_for_matching",
    "to_cyrillic",
    "to_latin",
]
