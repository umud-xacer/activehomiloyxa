"""Reads `MediaAsset` snapshots from `media` -- never `media.domain`/`application`/
`infrastructure` (`cross-module-profiles`, tools/importlinter.cfg; X-06: "Profiles ... hold
`MediaAssetRef` only"). Mirrors `catalog.infrastructure.media_adapter`'s narrow-Protocol bridge
pattern exactly.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from profiles.application.ports import MediaAssetSnapshot


class _MediaReader(Protocol):
    """The narrow slice of `media.interfaces.ports.MediaIntakePort` this module actually calls."""

    async def get_media(self, media_id: UUID) -> object: ...


class MediaAssetReaderAdapter:
    """Implements `profiles.application.ports.MediaAssetReaderPort`."""

    def __init__(self, media: _MediaReader) -> None:
        self._media = media

    async def get_media_asset(self, media_asset_id: UUID) -> MediaAssetSnapshot | None:
        try:
            asset = await self._media.get_media(media_asset_id)
        except Exception:
            return None
        return MediaAssetSnapshot(
            id=asset.id,  # type: ignore[attr-defined]
            scan_status=asset.scan_status,  # type: ignore[attr-defined]
        )
