"""catalog -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from catalog.interfaces.dto import (
    AddFavoriteBody,
    Favorite,
    FavoritePage,
    ImageReorderRequest,
    Listing,
    ListingCreateRequest,
    ListingImage,
    ListingPage,
    ListingStatistics,
    ListingStatusChangeRequest,
    ListingUpdateRequest,
)


class ListingPort(Protocol):
    """Derived from OpenAPI operations: `addFavorite`, `attachListingImage`, `changeListingStatus`, `createListing`, `deleteListing`, `detachListingImage`, `getListing`, `getListingStatistics`, `listFavorites`, `listListingImages`, `listListings`, `listMyListings`, `removeFavorite`, `reorderListingImages`, `updateListing`."""

    async def add_favorite(self, body: AddFavoriteBody) -> Favorite:
        """`POST /me/favorites` (operationId `addFavorite`). Add a favorite"""
        ...

    async def attach_listing_image(self, listing_id: UUID, body: ListingImage) -> ListingImage:
        """`POST /listings/{listingId}/images` (operationId `attachListingImage`). Attach an image to a listing"""
        ...

    async def change_listing_status(
        self, listing_id: UUID, body: ListingStatusChangeRequest
    ) -> Listing:
        """`POST /listings/{listingId}/status` (operationId `changeListingStatus`). Change listing lifecycle state"""
        ...

    async def create_listing(self, body: ListingCreateRequest) -> Listing:
        """`POST /listings` (operationId `createListing`). Create a listing (draft or published)"""
        ...

    async def delete_listing(self, listing_id: UUID) -> None:
        """`DELETE /listings/{listingId}` (operationId `deleteListing`). Delete a listing"""
        ...

    async def detach_listing_image(self, listing_id: UUID, image_id: UUID) -> None:
        """`DELETE /listings/{listingId}/images/{imageId}` (operationId `detachListingImage`). Remove a listing image"""
        ...

    async def get_listing(self, listing_id: UUID, fields: str | None = None) -> Listing:
        """`GET /listings/{listingId}` (operationId `getListing`). Get listing detail"""
        ...

    async def get_listing_statistics(self, listing_id: UUID) -> ListingStatistics:
        """`GET /listings/{listingId}/statistics` (operationId `getListingStatistics`). Get listing statistics (owner)"""
        ...

    async def list_favorites(
        self, cursor: str | None = None, limit: int | None = 20
    ) -> FavoritePage:
        """`GET /me/favorites` (operationId `listFavorites`). List favorites"""
        ...

    async def list_listing_images(self, listing_id: UUID) -> list[ListingImage]:
        """`GET /listings/{listingId}/images` (operationId `listListingImages`). List listing images"""
        ...

    async def list_listings(
        self,
        cursor: str | None = None,
        limit: int | None = 20,
        fields: str | None = None,
        category_id: UUID | None = None,
        listing_type: Literal["ADVERTISEMENT", "PRODUCT", "SERVICE"] | None = None,
    ) -> ListingPage:
        """`GET /listings` (operationId `listListings`). Browse listings"""
        ...

    async def list_my_listings(
        self,
        cursor: str | None = None,
        limit: int | None = 20,
        state: Literal[
            "DRAFT",
            "PENDING_VERIFICATION",
            "PUBLISHED",
            "EDITED",
            "SUSPENDED",
            "ARCHIVED",
            "DELETED",
        ]
        | None = None,
    ) -> ListingPage:
        """`GET /me/listings` (operationId `listMyListings`). List my listings"""
        ...

    async def remove_favorite(self, listing_id: UUID) -> None:
        """`DELETE /me/favorites/{listingId}` (operationId `removeFavorite`). Remove a favorite"""
        ...

    async def reorder_listing_images(
        self, listing_id: UUID, body: ImageReorderRequest
    ) -> list[ListingImage]:
        """`PUT /listings/{listingId}/images` (operationId `reorderListingImages`). Reorder listing images"""
        ...

    async def update_listing(self, listing_id: UUID, body: ListingUpdateRequest) -> Listing:
        """`PUT /listings/{listingId}` (operationId `updateListing`). Edit a listing"""
        ...
