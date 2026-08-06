"""profiles -- the `PortfolioItem` child entity (DDD Sec 5.2: "Entities: PortfolioItem (ordered
image references)"). Owns no repository of its own -- persisted as part of
`BusinessProfileRepository`'s unit of work, mirroring `catalog.domain.ImageAttachment`'s role.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared_kernel import LocalizedText


@dataclass(frozen=True)
class PortfolioItem:
    """`media_asset_id` is a `MediaAssetRef` only (X-06: profiles "hold MediaAssetRef only") --
    never a storage key or other media-internal detail. No status field: unlike
    `catalog.domain.ImageAttachment`, Physical DB `profiles.portfolio_item` carries no
    scan-status column -- `infrastructure.event_projection`'s media consumer removes the item
    entirely on `MediaAssetRejected` rather than flipping a status (see that module's docstring)."""

    id: UUID
    media_asset_id: UUID
    position: int
    caption: LocalizedText | None
    created_at: datetime
