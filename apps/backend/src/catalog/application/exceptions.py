"""catalog/application -- exceptions for facts the domain layer cannot know (missing rows,
cross-module lookups, optimistic-concurrency conflicts). Mirrors `media.application.exceptions`'s
style: one base, typed subclasses named for the invariant/condition they signal."""

from __future__ import annotations

from uuid import UUID

from shared_kernel import ListingId


class CatalogApplicationError(Exception):
    """Base for every typed exception raised by catalog's application/ layer."""


class ListingNotFoundError(CatalogApplicationError):
    def __init__(self, listing_id: ListingId | UUID) -> None:
        self.listing_id = listing_id
        super().__init__(f"listing {listing_id} not found")


class FavoriteNotFoundError(CatalogApplicationError):
    def __init__(self, listing_id: UUID) -> None:
        self.listing_id = listing_id
        super().__init__(f"no favorite on listing {listing_id} for this caller")


class CategoryNotFoundError(CatalogApplicationError):
    def __init__(self, category_id: UUID) -> None:
        self.category_id = category_id
        super().__init__(f"category {category_id} not found")


class CategoryFormUnavailableError(CatalogApplicationError):
    """The category has no published bound form to validate against (I-02's "the one bound
    form" is missing or unpublished) -- a configuration-authoring gap, not a caller error, but
    still not something catalog can silently work around (DEC-21: never invent a default form)."""

    def __init__(self, category_id: UUID) -> None:
        self.category_id = category_id
        super().__init__(f"category {category_id} has no published bound form")


class ListingMediaAssetNotFoundError(CatalogApplicationError):
    """Distinct from `media.application.exceptions.MediaAssetNotFoundError` -- catalog never
    imports media's own exception type (`cross-module-catalog`, tools/importlinter.cfg); this is
    catalog's own typed fact about a media asset id it could not resolve via
    `MediaAssetReaderPort`."""

    def __init__(self, media_asset_id: UUID) -> None:
        self.media_asset_id = media_asset_id
        super().__init__(f"media asset {media_asset_id} not found")


class StaleListingVersionError(CatalogApplicationError):
    """Optimistic-concurrency conflict (OpenAPI `Listing.lockVersion` "echo it on update"): the
    caller's `lockVersion` no longer matches the persisted listing. Raised by the use case
    *before* any domain method runs (an explicit compare against the freshly loaded aggregate,
    not merely relying on `backbone.persistence.AggregateMixin`'s `version_id_col`, which only
    guards an intra-request race -- see `catalog/application/listing_use_cases.py`)."""

    def __init__(self, listing_id: ListingId, *, expected: int, actual: int) -> None:
        self.listing_id = listing_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"listing {listing_id} lockVersion mismatch: expected {expected}, is {actual}"
        )
