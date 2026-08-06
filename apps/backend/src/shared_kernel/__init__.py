"""shared_kernel -- zero-dependency value objects every module may import (DDD Sec 5.14).

MAY statically import: nothing (SAD Sec 8.1). MUST NOT contain business behaviour.
"""

from shared_kernel.events import EventEnvelope
from shared_kernel.outbox import OutboxPort
from shared_kernel.value_objects import (
    BusinessProfileId,
    CurrencyMismatchError,
    GeoLocation,
    ListingId,
    Locale,
    LocalizedText,
    MediaAssetId,
    Money,
    TypedId,
    UserId,
    ValidityPeriod,
)

__all__ = [
    "BusinessProfileId",
    "CurrencyMismatchError",
    "EventEnvelope",
    "GeoLocation",
    "ListingId",
    "Locale",
    "LocalizedText",
    "MediaAssetId",
    "Money",
    "OutboxPort",
    "TypedId",
    "UserId",
    "ValidityPeriod",
]
