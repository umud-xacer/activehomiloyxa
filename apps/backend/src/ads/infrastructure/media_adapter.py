"""Reads `MediaAsset` scan status from `media` -- never `media.domain`/`application`/
`infrastructure` (`cross-module-ads`, tools/importlinter.cfg; I-20). Mirrors `catalog.
infrastructure.media_adapter.MediaAssetReaderAdapter`'s narrow-Protocol bridge pattern exactly.
Called synchronously only at operator admin actions (create/update/schedule/resume) -- never at
serve time, which reads only the campaign's own locally cached `creative_status`.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ads.domain import CreativeStatus


class _MediaReader(Protocol):
    """The narrow slice of `media.interfaces.ports.MediaIntakePort` this module actually calls."""

    async def get_media(self, media_id: UUID) -> object: ...


class MediaCreativeStatusAdapter:
    """Implements `ads.application.ports.CreativeReaderPort`."""

    def __init__(self, media: _MediaReader) -> None:
        self._media = media

    async def get_creative_status(self, media_asset_id: UUID) -> CreativeStatus:
        """Fails closed to `PENDING` (never delivered, I-20) rather than raising, on the same
        "asset not found/media unreachable" ambiguity `catalog.infrastructure.media_adapter`'s
        own docstring already documents for `getMedia`'s lack of a 404 distinction."""
        try:
            asset = await self._media.get_media(media_asset_id)
        except Exception:
            return CreativeStatus.PENDING
        return CreativeStatus(asset.scan_status)  # type: ignore[attr-defined]
