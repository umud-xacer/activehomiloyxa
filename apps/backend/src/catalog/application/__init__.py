"""catalog/application -- use cases + ports (Task P-07). Depends only on `catalog.domain`,
`shared_kernel`, and `contracts.events.catalog`."""

from __future__ import annotations

from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.exceptions import (
    CatalogApplicationError,
    CategoryFormUnavailableError,
    CategoryNotFoundError,
    FavoriteNotFoundError,
    ListingMediaAssetNotFoundError,
    ListingNotFoundError,
    StaleListingVersionError,
)
from catalog.application.favorite_use_cases import FavoriteUseCases
from catalog.application.listing_use_cases import ListingUseCases
from catalog.application.ports import (
    CatalogPlatformSettings,
    CategoryFormPort,
    CategorySnapshot,
    FavoriteRepository,
    FormBinding,
    ListingRepository,
    MediaAssetReaderPort,
    MediaAssetSnapshot,
    PlatformSettingsReaderPort,
    SubscriptionSnapshot,
    SubscriptionSnapshotRepository,
)
from catalog.application.quota_service import QuotaEnforcementService

__all__ = [
    "CatalogApplicationError",
    "CatalogPlatformSettings",
    "CategoryFormPort",
    "CategoryFormUnavailableError",
    "CategoryNotFoundError",
    "CategorySnapshot",
    "DuplicateDetectionService",
    "FavoriteNotFoundError",
    "FavoriteRepository",
    "FavoriteUseCases",
    "FormBinding",
    "ListingMediaAssetNotFoundError",
    "ListingNotFoundError",
    "ListingRepository",
    "ListingUseCases",
    "MediaAssetReaderPort",
    "MediaAssetSnapshot",
    "PlatformSettingsReaderPort",
    "QuotaEnforcementService",
    "StaleListingVersionError",
    "SubscriptionSnapshot",
    "SubscriptionSnapshotRepository",
]
