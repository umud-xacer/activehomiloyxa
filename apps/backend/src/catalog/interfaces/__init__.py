"""catalog.interfaces -- the module's only importable public surface (AIR-02)."""

from __future__ import annotations

from catalog.interfaces.auth import ActingUser
from catalog.interfaces.dto import (
    AddFavoriteBody,
    Favorite,
    FavoritePage,
    ImageReorderRequest,
    Listing,
    ListingCreateRequest,
    ListingImage,
    ListingPage,
    ListingPromotion,
    ListingStatistics,
    ListingStatusChangeRequest,
    ListingUpdateRequest,
)
from catalog.interfaces.errors import register_catalog_exception_mappings
from catalog.interfaces.moderation_port import (
    CatalogListingModerationAdapter,
    ListingModerationPort,
)
from catalog.interfaces.ports import (
    ListingPort,
)
from catalog.interfaces.routers import catalog_router, favorites_router

__all__ = [
    "ActingUser",
    "AddFavoriteBody",
    "CatalogListingModerationAdapter",
    "Favorite",
    "FavoritePage",
    "ImageReorderRequest",
    "Listing",
    "ListingCreateRequest",
    "ListingImage",
    "ListingModerationPort",
    "ListingPage",
    "ListingPort",
    "ListingPromotion",
    "ListingStatistics",
    "ListingStatusChangeRequest",
    "ListingUpdateRequest",
    "catalog_router",
    "favorites_router",
    "register_catalog_exception_mappings",
]
