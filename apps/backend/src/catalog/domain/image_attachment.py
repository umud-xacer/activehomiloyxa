"""catalog -- the `ImageAttachment` child entity (DDD Sec 5.3: "Entities: ImageAttachment
(ordered, <=10 -- BRULE-06; holds MediaAssetRef + processing status)"). Owns no repository of its
own -- persisted as part of `ListingRepository`'s unit of work, mirroring
`media.domain.ImageVariant`'s role inside `MediaAsset`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from catalog.domain.value_objects import ImageStatus


@dataclass(frozen=True)
class ImageAttachment:
    """`media_asset_id` is a `MediaAssetRef` only (X-06: "Owners hold MediaAssetRef only") --
    catalog never stores a storage key or any other media-internal detail. `status` is the
    projected `asset_status_snapshot`, event-maintained from media's `MediaAssetReady`/
    `MediaAssetRejected` (I-04's `[E]` half); it starts `PENDING` at attach time since scanning
    is asynchronous (QR-05: attaching never blocks on media's own pipeline)."""

    id: UUID
    media_asset_id: UUID
    position: int
    status: ImageStatus
    created_at: datetime
