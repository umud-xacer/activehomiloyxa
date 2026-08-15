"""`SqlalchemyMediaAssetRepository` -- implements `application.ports.MediaAssetRepository`
against Postgres. Maps the persistence-ignorant `MediaAsset` aggregate to/from ORM rows (DB
Architecture Sec 18 "mapping lives in infrastructure/"). Child rows (`ImageVariantRow`) are
replaced wholesale on every `save()` -- mirrors
`identity.infrastructure.persistence.repository.SqlalchemyUserAccountRepository`'s strategy and
its parent-before-children flush ordering (no ORM `relationship()` linking `MediaAssetRow`/
`ImageVariantRow`, so SQLAlchemy's unit-of-work does not reliably order cross-class INSERTs
within one flush without it).
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from media.domain import (
    ContentType,
    ImageVariant,
    MediaAsset,
    OwnerContextType,
    ProcessingStatus,
    ScanStatus,
    VariantKind,
)
from media.infrastructure.persistence.models import ImageVariantRow, MediaAssetRow
from shared_kernel import MediaAssetId, UserId


def _variant_to_domain(row: ImageVariantRow) -> ImageVariant:
    return ImageVariant(
        id=row.id,
        variant_kind=VariantKind(row.variant_kind),
        storage_key=row.storage_key,
        width_px=row.width_px,
        height_px=row.height_px,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )


def _asset_to_domain(row: MediaAssetRow, variant_rows: list[ImageVariantRow]) -> MediaAsset:
    return MediaAsset(
        id=MediaAssetId(value=row.id),
        owner_context_type=OwnerContextType(row.owner_context_type),
        owner_context_id=row.owner_context_id,
        storage_key=row.storage_key,
        content_type=ContentType(row.content_type),
        size_bytes=row.size_bytes,
        scan_status=ScanStatus(row.scan_status),
        processing_status=ProcessingStatus(row.processing_status),
        exif_stripped=row.exif_stripped,
        uploaded_by=UserId(value=row.uploaded_by),
        variants=tuple(_variant_to_domain(v) for v in variant_rows),
        created_at=row.created_at,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
        duration_seconds=row.duration_seconds,
    )


def _variant_row(asset_id: MediaAssetId, variant: ImageVariant) -> ImageVariantRow:
    return ImageVariantRow(
        id=variant.id,
        media_asset_id=asset_id.value,
        variant_kind=variant.variant_kind.value,
        storage_key=variant.storage_key,
        width_px=variant.width_px,
        height_px=variant.height_px,
        size_bytes=variant.size_bytes,
        created_at=variant.created_at,
    )


class SqlalchemyMediaAssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, asset_id: MediaAssetId) -> MediaAsset | None:
        row = await self._session.get(MediaAssetRow, asset_id.value)
        return await self._hydrate(row) if row is not None else None

    async def add(self, asset: MediaAsset) -> None:
        self._session.add(self._asset_row(asset))
        await self._session.flush()
        for variant in asset.variants:
            self._session.add(_variant_row(asset.id, variant))

    async def save(self, asset: MediaAsset) -> None:
        row = await self._session.get(MediaAssetRow, asset.id.value)
        if row is None:
            raise LookupError(f"MediaAssetRow {asset.id.value} not found for save()")
        row.owner_context_type = asset.owner_context_type.value
        row.owner_context_id = asset.owner_context_id
        row.storage_key = asset.storage_key
        row.content_type = asset.content_type.value
        row.size_bytes = asset.size_bytes
        row.scan_status = asset.scan_status.value
        row.processing_status = asset.processing_status.value
        row.exif_stripped = asset.exif_stripped
        row.uploaded_by = asset.uploaded_by.value
        row.duration_seconds = asset.duration_seconds
        row.updated_at = asset.updated_at

        await self._session.execute(
            delete(ImageVariantRow).where(ImageVariantRow.media_asset_id == asset.id.value)
        )
        await self._session.flush()
        for variant in asset.variants:
            self._session.add(_variant_row(asset.id, variant))

    async def delete(self, asset_id: MediaAssetId) -> None:
        """`ImageVariantRow`s cascade at the database level (`ON DELETE CASCADE`, Physical DB
        Sec 2.6) -- no explicit child delete needed."""
        await self._session.execute(delete(MediaAssetRow).where(MediaAssetRow.id == asset_id.value))

    async def list_pending_scan(self, *, limit: int) -> list[MediaAsset]:
        result = await self._session.execute(
            select(MediaAssetRow)
            .where(MediaAssetRow.scan_status == ScanStatus.PENDING.value)
            .order_by(MediaAssetRow.created_at)
            .limit(limit)
        )
        rows = list(result.scalars().all())
        return [await self._hydrate(row) for row in rows]

    async def list_pending_processing(self, *, limit: int) -> list[MediaAsset]:
        result = await self._session.execute(
            select(MediaAssetRow)
            .where(
                MediaAssetRow.scan_status == ScanStatus.CLEAN.value,
                MediaAssetRow.processing_status == ProcessingStatus.PENDING.value,
            )
            .order_by(MediaAssetRow.created_at)
            .limit(limit)
        )
        rows = list(result.scalars().all())
        return [await self._hydrate(row) for row in rows]

    async def _hydrate(self, row: MediaAssetRow) -> MediaAsset:
        result = await self._session.execute(
            select(ImageVariantRow).where(ImageVariantRow.media_asset_id == row.id)
        )
        return _asset_to_domain(row, list(result.scalars().all()))

    @staticmethod
    def _asset_row(asset: MediaAsset) -> MediaAssetRow:
        return MediaAssetRow(
            id=asset.id.value,
            owner_context_type=asset.owner_context_type.value,
            owner_context_id=asset.owner_context_id,
            storage_key=asset.storage_key,
            content_type=asset.content_type.value,
            size_bytes=asset.size_bytes,
            scan_status=asset.scan_status.value,
            processing_status=asset.processing_status.value,
            exif_stripped=asset.exif_stripped,
            uploaded_by=asset.uploaded_by.value,
            duration_seconds=asset.duration_seconds,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
            lock_version=asset.lock_version,
        )
