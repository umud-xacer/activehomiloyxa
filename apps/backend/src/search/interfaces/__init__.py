"""search.interfaces -- the module's only importable public surface (AIR-02)."""

from __future__ import annotations

from search.interfaces.dto import (
    CursorPagePage,
    Facet,
    FacetBuckets,
    SearchHit,
    SearchHitPromoted,
    SearchRequest,
    SearchRequestGeo,
    SearchResult,
    Suggestion,
)
from search.interfaces.errors import register_search_exception_mappings
from search.interfaces.ports import (
    SearchQueryPort,
)
from search.interfaces.routers import search_router

__all__ = [
    "CursorPagePage",
    "Facet",
    "FacetBuckets",
    "SearchHit",
    "SearchHitPromoted",
    "SearchQueryPort",
    "SearchRequest",
    "SearchRequestGeo",
    "SearchResult",
    "Suggestion",
    "register_search_exception_mappings",
    "search_router",
]
