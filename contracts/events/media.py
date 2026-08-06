"""media (BC-06) domain events -- DDD Sec 6, the authoritative v1 event catalogue.

STATUS: frozen (Task P-06, ADR-0001). DDD Sec 6's published table has no BC-06 row (a gap
`contracts/README.md` recorded explicitly under Task P-01); ADR-0001
(`docs/adr/0001-media-asset-status-events.md`) resolves it by adding these three events, per SAD
Sec 7.2's public-interface column ("MediaIntakePort, asset-status events") and DDD's own X-06
cross-context integration row ("Media pushes ScanCompleted/ProcessingCompleted status"). Schema
only: each class is the shared envelope (`shared_kernel.EventEnvelope`) with `event_type` pinned
to its own past-tense name. No publishing logic, no handlers -- that is outbox/adapter work for
this same task's `infrastructure/`. Do not add an event here beyond ADR-0001's three; do not
remove one either without a further ADR amending this one.
"""

from __future__ import annotations

from typing import Literal

from shared_kernel import EventEnvelope


class MediaAssetAccepted(EventEnvelope):
    """Emitted when: an upload is registered as intake-valid (type/size checked) and admitted
    to the processing pipeline.

    Principal consumers: none in v1 (informational audit trail; reserved for a future task).
    """

    event_type: Literal["MediaAssetAccepted"] = "MediaAssetAccepted"


class MediaAssetReady(EventEnvelope):
    """Emitted when: scanning and processing both complete successfully (Clean + Completed);
    the asset becomes delivery-available.

    Principal consumers: Catalog, Profiles, Ads.
    """

    event_type: Literal["MediaAssetReady"] = "MediaAssetReady"


class MediaAssetRejected(EventEnvelope):
    """Emitted when: scanning quarantines the asset, or processing fails terminally; the asset
    never becomes delivery-available (I-20 QuarantinePolicy).

    Principal consumers: Catalog, Profiles, Ads.
    """

    event_type: Literal["MediaAssetRejected"] = "MediaAssetRejected"
