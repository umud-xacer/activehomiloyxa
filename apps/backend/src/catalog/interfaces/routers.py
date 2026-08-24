"""FastAPI routers implementing exactly the fifteen catalog-tagged OpenAPI operations
(`contracts/openapi.yaml`) -- no more, no less (P-07 prompt scope). Thin translation only:
cookie/body -> use-case call -> domain object -> already-frozen `interfaces/dto.py` DTO. All
business logic lives in `application`/`domain`; this module owns none. Mirrors `media.interfaces.
routers`'s pattern exactly.

Three operations (`listListings`/`getListing`/`listListingImages`) declare `security: []` in
`contracts/openapi.yaml` -- they use `get_optional_acting_user` (never raises on a missing
session) rather than `get_acting_user`; every other operation requires a session.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends

from catalog.application import FavoriteUseCases, ListingNotFoundError, ListingUseCases
from catalog.domain.exceptions import NotListingOwnerError
from catalog.domain.image_attachment import ImageAttachment as DomainImageAttachment
from catalog.domain.listing import Listing as DomainListing
from catalog.domain.value_objects import ListingType
from catalog.interfaces.auth import ActingUser
from catalog.interfaces.di import (
    get_acting_user,
    get_favorite_use_cases,
    get_listing_use_cases,
    get_optional_acting_user,
)
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
    PageInfo,
)
from shared_kernel import ListingId

catalog_router = APIRouter(tags=["Catalog"])
favorites_router = APIRouter(tags=["Favorites"])


def _image_to_dto(image: DomainImageAttachment) -> ListingImage:
    return ListingImage(
        id=image.id,
        media_asset_id=image.media_asset_id,
        position=image.position,
        status=image.status.value,
    )


def _listing_to_dto(listing: DomainListing) -> Listing:
    return Listing(
        id=listing.id.value,
        listing_type=listing.listing_type.value,
        owner_user_id=listing.owner_user_id.value,
        owner_profile_id=listing.owner_profile_id.value
        if listing.owner_profile_id
        else None,
        category_id=listing.category_id,
        category_path=listing.category_path,
        form_definition_version_id=listing.form_definition_version_id,
        title=listing.title,
        description=listing.description,
        attributes=listing.attributes,
        price=listing.price,
        location=listing.location,
        lifecycle_state=listing.lifecycle_state.value,
        is_flagged=listing.is_flagged,
        expires_at=listing.expires_at,
        published_at=listing.published_at,
        promotion=(
            ListingPromotion(
                kind=listing.promotion.kind.value,
                valid_until=listing.promotion.valid_until,
            )
            if listing.promotion
            else None
        ),
        images=[_image_to_dto(i) for i in listing.images],
        slug=listing.slug,
        lock_version=listing.lock_version,
        awaiting_payment=listing.awaiting_payment,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
    )


# --- listings: public browse/detail ---------------------------------------------------------


@catalog_router.get("/listings", operation_id="listListings")
async def list_listings(
    cursor: str | None = None,
    limit: int | None = 20,
    fields: str | None = None,
    categoryId: UUID | None = None,
    listingType: str | None = None,
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> ListingPage:
    page_limit = limit or 20
    listings, next_cursor = await use_cases.list_public_listings(
        category_id=categoryId,
        listing_type=listingType,
        cursor=cursor,
        limit=page_limit,
        now=datetime.now(UTC),
    )
    return ListingPage(
        items=[_listing_to_dto(item) for item in listings],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


@catalog_router.get("/listings/{listingId}", operation_id="getListing")
async def get_listing(
    listingId: UUID,
    fields: str | None = None,
    acting_user: ActingUser | None = Depends(get_optional_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> Listing:
    listing = await use_cases.get_listing(ListingId(value=listingId))
    is_owner = (
        acting_user is not None and acting_user.account_id == listing.owner_user_id
    )
    if not is_owner and not listing.is_publicly_visible(now=datetime.now(UTC)):
        # Non-owners never learn a non-visible listing exists (I-06's own visibility rule).
        raise ListingNotFoundError(listing.id)
    # UNF-015/FR-ADV-010: recorded only once visibility has already passed -- a blocked peek at
    # a non-visible listing never counts as a view.
    await use_cases.record_view(
        listing.id,
        viewer_user_id=acting_user.account_id if acting_user else None,
        now=datetime.now(UTC),
    )
    return _listing_to_dto(listing)


@catalog_router.get("/listings/{listingId}/images", operation_id="listListingImages")
async def list_listing_images(
    listingId: UUID, use_cases: ListingUseCases = Depends(get_listing_use_cases)
) -> list[ListingImage]:
    images = await use_cases.list_images(ListingId(value=listingId))
    return [_image_to_dto(i) for i in images]


# --- listings: owner-authenticated write/query -----------------------------------------------


@catalog_router.post("/listings", operation_id="createListing", status_code=201)
async def create_listing(
    body: ListingCreateRequest,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> Listing:
    listing = await use_cases.create_listing(
        owner_user_id=acting_user.account_id,
        owner_profile_id=acting_user.acting_profile_id,
        listing_type=ListingType(body.listing_type),
        category_id=body.category_id,
        title=body.title,
        description=body.description,
        attributes=body.attributes,
        price=body.price,
        location=body.location,
        image_media_asset_ids=body.image_media_asset_ids,
        publish=bool(body.publish),
        auto_compute_payment_requirement=True,
        now=datetime.now(UTC),
    )
    return _listing_to_dto(listing)


@catalog_router.put("/listings/{listingId}", operation_id="updateListing")
async def update_listing(
    listingId: UUID,
    body: ListingUpdateRequest,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> Listing:
    listing = await use_cases.edit_listing(
        listing_id=ListingId(value=listingId),
        actor_user_id=acting_user.account_id,
        expected_lock_version=body.lock_version,
        title=body.title,
        description=body.description,
        attributes=body.attributes,
        price=body.price,
        location=body.location,
        now=datetime.now(UTC),
    )
    return _listing_to_dto(listing)


@catalog_router.delete(
    "/listings/{listingId}", operation_id="deleteListing", status_code=204
)
async def delete_listing(
    listingId: UUID,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> None:
    await use_cases.delete_listing(
        listing_id=ListingId(value=listingId),
        actor_user_id=acting_user.account_id,
        now=datetime.now(UTC),
    )


@catalog_router.post("/listings/{listingId}/status", operation_id="changeListingStatus")
async def change_listing_status(
    listingId: UUID,
    body: ListingStatusChangeRequest,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> Listing:
    listing = await use_cases.change_status(
        listing_id=ListingId(value=listingId),
        actor_user_id=acting_user.account_id,
        action=body.action,
        reason=body.reason,
        now=datetime.now(UTC),
    )
    return _listing_to_dto(listing)


@catalog_router.post(
    "/listings/{listingId}/images", operation_id="attachListingImage", status_code=201
)
async def attach_listing_image(
    listingId: UUID,
    body: ListingImage,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> ListingImage:
    image = await use_cases.attach_image(
        listing_id=ListingId(value=listingId),
        actor_user_id=acting_user.account_id,
        media_asset_id=body.media_asset_id,
        now=datetime.now(UTC),
    )
    return _image_to_dto(image)


@catalog_router.put("/listings/{listingId}/images", operation_id="reorderListingImages")
async def reorder_listing_images(
    listingId: UUID,
    body: ImageReorderRequest,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> list[ListingImage]:
    images = await use_cases.reorder_images(
        listing_id=ListingId(value=listingId),
        actor_user_id=acting_user.account_id,
        ordered_image_ids=tuple(body.order),
        now=datetime.now(UTC),
    )
    return [_image_to_dto(i) for i in images]


@catalog_router.delete(
    "/listings/{listingId}/images/{imageId}",
    operation_id="detachListingImage",
    status_code=204,
)
async def detach_listing_image(
    listingId: UUID,
    imageId: UUID,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> None:
    await use_cases.detach_image(
        listing_id=ListingId(value=listingId),
        actor_user_id=acting_user.account_id,
        image_id=imageId,
        now=datetime.now(UTC),
    )


@catalog_router.get(
    "/listings/{listingId}/statistics", operation_id="getListingStatistics"
)
async def get_listing_statistics(
    listingId: UUID,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
    favorite_use_cases: FavoriteUseCases = Depends(get_favorite_use_cases),
) -> ListingStatistics:
    listing = await use_cases.get_listing(ListingId(value=listingId))
    if listing.owner_user_id != acting_user.account_id:
        raise NotListingOwnerError(listingId)
    favorites_count = await favorite_use_cases.count_for_listing(listing.id)
    return ListingStatistics(
        listing_id=listingId,
        views=None,
        contact_clicks=None,
        phone_reveals=None,
        chats_initiated=None,
        favorites=favorites_count,
    )


@catalog_router.get("/me/listings", operation_id="listMyListings")
async def list_my_listings(
    cursor: str | None = None,
    limit: int | None = 20,
    state: str | None = None,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: ListingUseCases = Depends(get_listing_use_cases),
) -> ListingPage:
    page_limit = limit or 20
    listings, next_cursor = await use_cases.list_my_listings(
        owner_user_id=acting_user.account_id,
        state=state,
        cursor=cursor,
        limit=page_limit,
    )
    return ListingPage(
        items=[_listing_to_dto(item) for item in listings],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


# --- favorites (FR-USER-004) -------------------------------------------------------------------


@favorites_router.get("/me/favorites", operation_id="listFavorites")
async def list_favorites(
    cursor: str | None = None,
    limit: int | None = 20,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: FavoriteUseCases = Depends(get_favorite_use_cases),
) -> FavoritePage:
    page_limit = limit or 20
    favorites, next_cursor = await use_cases.list_favorites(
        user_id=acting_user.account_id, cursor=cursor, limit=page_limit
    )
    return FavoritePage(
        items=[
            Favorite(listing_id=f.listing_id.value, created_at=f.created_at)
            for f in favorites
        ],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


@favorites_router.post("/me/favorites", operation_id="addFavorite", status_code=201)
async def add_favorite(
    body: AddFavoriteBody,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: FavoriteUseCases = Depends(get_favorite_use_cases),
) -> Favorite:
    favorite = await use_cases.add_favorite(
        user_id=acting_user.account_id,
        listing_id=ListingId(value=body.listing_id),
        now=datetime.now(UTC),
    )
    return Favorite(
        listing_id=favorite.listing_id.value, created_at=favorite.created_at
    )


@favorites_router.delete(
    "/me/favorites/{listingId}", operation_id="removeFavorite", status_code=204
)
async def remove_favorite(
    listingId: UUID,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: FavoriteUseCases = Depends(get_favorite_use_cases),
) -> None:
    await use_cases.remove_favorite(
        user_id=acting_user.account_id,
        listing_id=ListingId(value=listingId),
        now=datetime.now(UTC),
    )
