"""media -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from media.interfaces.dto import (
    MediaAsset,
    MediaUploadInitRequest,
    MediaUploadInitResponse,
)


class MediaIntakePort(Protocol):
    """Derived from OpenAPI operations: `deleteMedia`, `getMedia`, `initMediaUpload`."""

    async def delete_media(self, media_id: UUID) -> None:
        """`DELETE /media/{mediaId}` (operationId `deleteMedia`). Delete a media asset"""
        ...

    async def get_media(self, media_id: UUID) -> MediaAsset:
        """`GET /media/{mediaId}` (operationId `getMedia`). Get media metadata & preview URLs"""
        ...

    async def init_media_upload(self, body: MediaUploadInitRequest) -> MediaUploadInitResponse:
        """`POST /media/uploads` (operationId `initMediaUpload`). Initiate an image upload (presigned)"""
        ...
