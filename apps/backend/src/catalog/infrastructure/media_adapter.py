"""Reads `MediaAsset` snapshots from `media` -- never `media.domain`/`application`/
`infrastructure` (`cross-module-catalog`, tools/importlinter.cfg; X-06: "Catalog ... hold
`MediaAssetRef` only"). Mirrors `catalog.infrastructure.configuration_adapter`'s narrow-Protocol
bridge pattern.

`media.interfaces.dto.MediaAsset` (the only shape `MediaIntakePort.get_media` -- the sole
sanctioned crossing point -- returns) carries no uploader/owner field: `getMedia`'s own docstring
("No ownership check -- contracts/openapi.yaml declares no 401/403 for this operation; delivery
metadata is meant to be readable by whatever page embeds the image") makes that a deliberate
choice in media's own design, not an oversight this adapter could work around. Attach-time
verification is therefore existence-only (`ListingMediaAssetNotFoundError`) -- there is no
sanctioned way for catalog to also confirm the caller uploaded this specific asset."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from catalog.application.ports import MediaAssetSnapshot


class _MediaReader(Protocol):
    """The narrow slice of `media.interfaces.ports.MediaIntakePort` this module actually calls."""

    async def get_media(self, media_id: UUID) -> object: ...


class MediaAssetReaderAdapter:
    """Implements `catalog.application.ports.MediaAssetReaderPort`."""

    def __init__(self, media: _MediaReader) -> None:
        self._media = media

    async def get_media_asset(self, media_asset_id: UUID) -> MediaAssetSnapshot | None:
        try:
            asset = await self._media.get_media(media_asset_id)
        except Exception:
            return None
        variants = getattr(asset, "variants", None) or []
        thumbnail = next(
            (v for v in variants if getattr(v, "kind", None) == "THUMBNAIL"),
            None,
        )
        return MediaAssetSnapshot(
            id=asset.id,  # type: ignore[attr-defined]
            scan_status=asset.scan_status,  # type: ignore[attr-defined]
            # Falls back to the original's URL when the THUMBNAIL variant is not written yet:
            # a correctly-sized image is preferable, but a full-size one still renders, and a
            # card with no image at all is the worse outcome.
            thumbnail_url=(
                getattr(thumbnail, "url", None)
                if thumbnail is not None
                else getattr(asset, "url", None)
            ),
        )
