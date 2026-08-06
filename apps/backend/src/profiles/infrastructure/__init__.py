"""profiles/infrastructure -- SQLAlchemy repositories, the media adapter, the badge-expiry sweep
worker, and idempotent cross-module event projection handlers (Task P-11). Never imported by
`profiles.interfaces`/`application`/`domain` -- only the composition root (outside every module's
package tree) wires these concrete classes behind the ports `application/` declares.
"""

from __future__ import annotations

from profiles.infrastructure.event_projection import (
    handle_entitlement_event,
    handle_media_event,
    handle_subscription_entitlement_event,
)
from profiles.infrastructure.media_adapter import MediaAssetReaderAdapter
from profiles.infrastructure.persistence import (
    SqlalchemyBusinessProfileRepository,
    SqlalchemySubscriptionEligibilityRepository,
    SqlalchemyVerificationCaseRepository,
    SqlalchemyVerificationEligibilityRepository,
)
from profiles.infrastructure.worker import BadgeExpiryWorker

__all__ = [
    "BadgeExpiryWorker",
    "MediaAssetReaderAdapter",
    "SqlalchemyBusinessProfileRepository",
    "SqlalchemySubscriptionEligibilityRepository",
    "SqlalchemyVerificationCaseRepository",
    "SqlalchemyVerificationEligibilityRepository",
    "handle_entitlement_event",
    "handle_media_event",
    "handle_subscription_entitlement_event",
]
