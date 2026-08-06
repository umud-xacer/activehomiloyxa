"""media -- the `ImageVariant` child entity (DDD Sec 5.6: "set of ImageVariant
(thumbnail/optimised -- FR-MEDIA-005)"; Physical DB `media.image_variant`, "child" with its own
`id` and `ON DELETE CASCADE` from `media_asset`). Owns no repository of its own -- persisted as
part of `MediaAssetRepository`'s unit of work, exactly like `identity.domain.AuthenticationMethod`
inside `UserAccount`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from media.domain.value_objects import VariantKind


@dataclass(frozen=True)
class ImageVariant:
    """`storage_key` is the internal MinIO object key for this variant's bytes -- never
    serialized to a DTO (Security Sec 7: "storage keys are opaque and never exposed as
    identity"); `interfaces/` builds the public delivery URL from the owning asset's id + this
    variant's `kind`, never from `storage_key` directly."""

    id: UUID
    variant_kind: VariantKind
    storage_key: str
    width_px: int
    height_px: int
    size_bytes: int
    created_at: datetime
