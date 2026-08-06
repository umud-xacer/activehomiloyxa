"""media/application -- exceptions for facts the domain layer cannot know (missing rows,
authorization facts). Mirrors `identity.application.exceptions`'s style."""

from __future__ import annotations

from shared_kernel import MediaAssetId


class MediaApplicationError(Exception):
    """Base for every typed exception raised by media's application/ layer."""


class MediaAssetNotFoundError(MediaApplicationError):
    def __init__(self, asset_id: MediaAssetId) -> None:
        self.asset_id = asset_id
        super().__init__(f"media asset {asset_id.value} not found")


class NotAssetOwnerError(MediaApplicationError):
    """`deleteMedia`'s "ownership validated" (`contracts/openapi.yaml`): the caller is not the
    account that uploaded this asset. Maps to 403 `PERMISSION_DENIED` -- `MediaAsset` has no
    concept of a granted permission key (self-service, upload-your-own scope only, mirroring
    identity's own self-service operations), so this is an ownership check, not an
    `AuthorizationPort` gate."""

    def __init__(self, asset_id: MediaAssetId) -> None:
        self.asset_id = asset_id
        super().__init__(f"caller does not own media asset {asset_id.value}")
