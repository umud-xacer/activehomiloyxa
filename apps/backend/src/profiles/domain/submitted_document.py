"""profiles -- the `SubmittedDocument` child entity (DDD Sec 5.2: "Entities: SubmittedDocument
(MediaAssetRef, document kind, images only -- FR-PROF-003)"). Owns no repository of its own --
persisted as part of `VerificationCaseRepository`'s unit of work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class SubmittedDocument:
    """`media_asset_id` is a `MediaAssetRef` only (X-06). Images-only (DEC-10) is enforced at
    media's own intake boundary (`media.interfaces.dto.MediaUploadInitRequest.content_type`'s
    closed image-whitelist Literal) -- by the time a `media_asset_id` reaches this entity it is
    already guaranteed to reference an image, the same "attach-time verification is
    existence-only" trust boundary `catalog.infrastructure.media_adapter`'s own docstring
    documents. `document_kind` is a reviewer-facing free-text label (Physical DB: "reviewer-facing
    label"), not a closed vocabulary."""

    id: UUID
    media_asset_id: UUID
    document_kind: str
    position: int
    created_at: datetime
