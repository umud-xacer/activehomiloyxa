"""FastAPI routers implementing exactly the three Media-tagged OpenAPI operations
(`contracts/openapi.yaml`) -- no more, no less (P-06 prompt scope). Thin translation only:
cookie/body -> use-case call -> domain object -> already-frozen `interfaces/dto.py` DTO. All
business logic lives in `application`/`domain`; this module owns none.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends

from backbone.persistence.env import required_env
from media.application import MediaIntakeUseCases
from media.domain import MediaAsset as DomainMediaAsset
from media.interfaces.auth import ActingUser
from media.interfaces.di import get_acting_user, get_media_intake_use_cases
from media.interfaces.dto import (
    MediaAsset,
    MediaAssetVariants,
    MediaUploadInitRequest,
    MediaUploadInitResponse,
)
from shared_kernel import MediaAssetId

media_router = APIRouter(tags=["Media"])


def _cdn_url_for(storage_key: str) -> str:
    """Security Sec 7 "storage keys are opaque and never exposed as identity": the only place a
    `storage_key` is read at all in `interfaces/` is here, to build a URL *string* -- the key
    itself is never assigned to a response field. `MEDIA_CDN_BASE_URL`'s origin is this same
    MinIO bucket (Infra Sec 4 "minio -.origin.-> cdn"), so the CDN path mirrors the object key
    1:1; `storage_key` is itself already built from the asset's own public id
    (`media.domain.media_asset._storage_key_for`), not a separately-invented secret, so this
    composition discloses nothing beyond what `MediaAsset.id` already does."""
    return f"{required_env('MEDIA_CDN_BASE_URL')}/{storage_key}"


def _asset_to_dto(asset: DomainMediaAsset) -> MediaAsset:
    deliverable = asset.is_delivery_available
    return MediaAsset(
        id=asset.id.value,
        owner_context_type=asset.owner_context_type.value,
        owner_context_id=asset.owner_context_id,
        content_type=asset.content_type.value,
        size_bytes=asset.size_bytes,
        scan_status=asset.scan_status.value,
        processing_status=asset.processing_status.value,
        url=_cdn_url_for(asset.storage_key) if deliverable else None,
        variants=(
            [
                MediaAssetVariants(
                    kind=variant.variant_kind.value,
                    url=_cdn_url_for(variant.storage_key),
                    width=variant.width_px,
                    height=variant.height_px,
                )
                for variant in asset.variants
            ]
            if deliverable and asset.variants
            else None
        ),
        duration_seconds=asset.duration_seconds,
        created_at=asset.created_at,
    )


@media_router.post("/media/uploads", operation_id="initMediaUpload", status_code=201)
async def init_media_upload(
    body: MediaUploadInitRequest,
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: MediaIntakeUseCases = Depends(get_media_intake_use_cases),
) -> MediaUploadInitResponse:
    asset, presigned = await use_cases.init_media_upload(
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        owner_context_type=body.owner_context_type,
        uploaded_by=acting_user.account_id,
        now=datetime.now(UTC),
    )
    return MediaUploadInitResponse(
        media_asset_id=asset.id.value,
        upload_url=presigned.upload_url,
        method=presigned.method,
        headers=presigned.headers,
        expires_at=presigned.expires_at,
    )


@media_router.get("/media/{mediaId}", operation_id="getMedia")
async def get_media(
    mediaId: UUID,  # must match the {mediaId} path template exactly (contracts/openapi.yaml)
    use_cases: MediaIntakeUseCases = Depends(get_media_intake_use_cases),
) -> MediaAsset:
    """Deliberately public, unlike `initMediaUpload`/`deleteMedia` -- `contracts/openapi.yaml`
    only documents 200/404 for this operation (no 401), and a listing/business-profile page must
    render its photos for an anonymous visitor, not only a logged-in one. Safe without a session:
    `_asset_to_dto` already gates `url`/`variants` on `is_delivery_available` (CLEAN + processed
    only), so a QUARANTINED/PENDING asset discloses no bytes regardless of caller; the id itself
    is an unguessable uuid, and the metadata returned (owner/content-type/status) carries nothing
    sensitive."""
    asset = await use_cases.get_media(MediaAssetId(value=mediaId))
    return _asset_to_dto(asset)


@media_router.delete("/media/{mediaId}", operation_id="deleteMedia", status_code=204)
async def delete_media(
    mediaId: UUID,  # must match the {mediaId} path template exactly (contracts/openapi.yaml)
    acting_user: ActingUser = Depends(get_acting_user),
    use_cases: MediaIntakeUseCases = Depends(get_media_intake_use_cases),
) -> None:
    await use_cases.delete_media(MediaAssetId(value=mediaId), requested_by=acting_user.account_id)
