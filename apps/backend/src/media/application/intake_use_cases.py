"""media/application -- self-service intake use cases backing `initMediaUpload`/`getMedia`/
`deleteMedia` (`MediaIntakePort`). Every method takes the caller's own `uploaded_by`/
`requested_by` `UserId` -- authorization (a valid session) is resolved by the router via
`ActingUser` before any of these run, the same self-service trust boundary
`identity.application.account_use_cases.AccountUseCases` documents for its own callers.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from contracts.events.media import MediaAssetAccepted
from media.application.exceptions import MediaAssetNotFoundError, NotAssetOwnerError
from media.application.ports import MediaAssetRepository, PresignedUpload, StoragePort
from media.domain import MediaAsset, OwnerContextType
from shared_kernel import MediaAssetId, OutboxPort, UserId


class MediaIntakeUseCases:
    def __init__(
        self,
        *,
        assets: MediaAssetRepository,
        storage: StoragePort,
        outbox: OutboxPort,
        presign_expiry_seconds: int,
    ) -> None:
        self._assets = assets
        self._storage = storage
        self._outbox = outbox
        self._presign_expiry_seconds = presign_expiry_seconds

    async def init_media_upload(
        self,
        *,
        content_type: str,
        size_bytes: int,
        owner_context_type: str,
        uploaded_by: UserId,
        now: datetime,
    ) -> tuple[MediaAsset, PresignedUpload]:
        """initMediaUpload. `MediaAsset.initiate` runs `ImageOnlyPolicy` + the size cap before
        anything is persisted or a presigned URL is issued -- an invalid request never reaches
        MinIO (Security Sec 7: "type + MIME ... verification ... before acceptance")."""
        asset = MediaAsset.initiate(
            asset_id=MediaAssetId(value=uuid4()),
            content_type_raw=content_type,
            size_bytes=size_bytes,
            owner_context_type=OwnerContextType(owner_context_type),
            uploaded_by=uploaded_by,
            now=now,
        )
        await self._assets.add(asset)
        presigned = await self._storage.generate_presigned_upload(
            storage_key=asset.storage_key,
            content_type=asset.content_type.value,
            expires_in_seconds=self._presign_expiry_seconds,
        )
        event = MediaAssetAccepted(
            event_id=uuid4(),
            occurred_at=now,
            actor=uploaded_by.value,
            aggregate_type="MediaAsset",
            aggregate_id=asset.id.value,
            payload={
                "mediaAssetId": str(asset.id.value),
                "ownerContextType": asset.owner_context_type.value,
                "contentType": asset.content_type.value,
            },
        )
        await self._outbox.append(event)
        return asset, presigned

    async def get_media(self, asset_id: MediaAssetId) -> MediaAsset:
        """getMedia. No ownership check -- `contracts/openapi.yaml` declares no 401/403 for this
        operation (delivery metadata is meant to be readable by whatever page embeds the
        image)."""
        return await self._require_asset(asset_id)

    async def delete_media(self, asset_id: MediaAssetId, *, requested_by: UserId) -> None:
        """deleteMedia. "Ownership validated" (`contracts/openapi.yaml`): raises
        `NotAssetOwnerError` (403) if `requested_by` did not upload this asset. Removes the
        object(s) from storage and the asset row together -- `contracts/openapi.yaml`'s own
        description ("bytes are cleaned up by the media lifecycle job") describes the *orphan/
        quarantine purge job* (Physical DB Sec 2.6, out of this task's scope, see
        `media/README.md`), not this synchronous delete, which removes what it can reach
        immediately."""
        asset = await self._require_asset(asset_id)
        if asset.uploaded_by != requested_by:
            raise NotAssetOwnerError(asset_id)
        await self._storage.delete_object(asset.storage_key)
        for variant in asset.variants:
            await self._storage.delete_object(variant.storage_key)
        await self._assets.delete(asset_id)

    async def _require_asset(self, asset_id: MediaAssetId) -> MediaAsset:
        asset = await self._assets.get_by_id(asset_id)
        if asset is None:
            raise MediaAssetNotFoundError(asset_id)
        return asset
