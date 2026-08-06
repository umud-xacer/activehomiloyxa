"""catalog/infrastructure -- SQLAlchemy repositories, configuration/media adapters, the expiry
sweep worker, and idempotent cross-module event projection handlers (Task P-07). Never imported
by `catalog.interfaces`/`application`/`domain` -- only the composition root (outside every
module's package tree) wires these concrete classes behind the ports `application/` declares."""

from __future__ import annotations

from catalog.infrastructure.configuration_adapter import (
    ConfigurationCategoryFormAdapter,
    ConfigurationPlatformSettingsAdapter,
)
from catalog.infrastructure.event_projection import (
    handle_entitlement_event,
    handle_identity_event,
    handle_media_event,
)
from catalog.infrastructure.media_adapter import MediaAssetReaderAdapter
from catalog.infrastructure.persistence import (
    SqlalchemyFavoriteRepository,
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from catalog.infrastructure.worker import CatalogExpiryWorker

__all__ = [
    "CatalogExpiryWorker",
    "ConfigurationCategoryFormAdapter",
    "ConfigurationPlatformSettingsAdapter",
    "MediaAssetReaderAdapter",
    "SqlalchemyFavoriteRepository",
    "SqlalchemyListingRepository",
    "SqlalchemySubscriptionSnapshotRepository",
    "handle_entitlement_event",
    "handle_identity_event",
    "handle_media_event",
]
