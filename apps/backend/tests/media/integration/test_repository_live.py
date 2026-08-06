"""Integration tests: `SqlalchemyMediaAssetRepository` round-trips against real PostgreSQL,
including child `ImageVariant` persistence, the `storage_key` uniqueness constraints, and the
`ON DELETE CASCADE` from `media_asset` to `image_variant` (Physical DB Sec 2.6)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from media.domain import ImageVariant, MediaAsset, OwnerContextType, VariantKind
from media.infrastructure.persistence.models import ImageVariantRow
from media.infrastructure.persistence.repository import SqlalchemyMediaAssetRepository
from shared_kernel import MediaAssetId, UserId

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _new_asset() -> MediaAsset:
    return MediaAsset.initiate(
        asset_id=MediaAssetId(value=uuid4()),
        content_type_raw="image/jpeg",
        size_bytes=1024,
        owner_context_type=OwnerContextType.LISTING,
        uploaded_by=UserId(value=uuid4()),
        now=NOW,
    )


def _variant(asset: MediaAsset, kind: VariantKind = VariantKind.THUMBNAIL) -> ImageVariant:
    return ImageVariant(
        id=uuid4(),
        variant_kind=kind,
        storage_key=f"media/{asset.id.value}/{kind.value.lower()}.jpg",
        width_px=200,
        height_px=200,
        size_bytes=10,
        created_at=NOW,
    )


async def test_add_and_get_by_id_round_trips(db_session: AsyncSession) -> None:
    repo = SqlalchemyMediaAssetRepository(db_session)
    asset = _new_asset()
    await repo.add(asset)
    await db_session.flush()

    fetched = await repo.get_by_id(asset.id)
    assert fetched is not None
    assert fetched.storage_key == asset.storage_key
    assert fetched.uploaded_by == asset.uploaded_by
    assert fetched.variants == ()


async def test_save_persists_scan_and_processing_transitions_and_variants(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyMediaAssetRepository(db_session)
    asset = _new_asset()
    await repo.add(asset)
    await db_session.flush()

    clean = asset.mark_scanned_clean(now=NOW)
    variant = _variant(clean)
    processed = clean.complete_processing(variants=(variant,), now=NOW)
    await repo.save(processed)
    await db_session.flush()

    fetched = await repo.get_by_id(asset.id)
    assert fetched is not None
    assert fetched.is_delivery_available is True
    assert fetched.exif_stripped is True
    assert len(fetched.variants) == 1
    assert fetched.variants[0].storage_key == variant.storage_key


async def test_save_replaces_variants_wholesale(db_session: AsyncSession) -> None:
    repo = SqlalchemyMediaAssetRepository(db_session)
    asset = _new_asset().mark_scanned_clean(now=NOW)
    await repo.add(asset)
    await db_session.flush()

    first_variant = _variant(asset, VariantKind.THUMBNAIL)
    processed = asset.complete_processing(variants=(first_variant,), now=NOW)
    await repo.save(processed)
    await db_session.flush()

    result = await db_session.execute(
        select(ImageVariantRow).where(ImageVariantRow.media_asset_id == asset.id.value)
    )
    assert len(result.scalars().all()) == 1


async def test_delete_cascades_to_image_variant_rows(db_session: AsyncSession) -> None:
    repo = SqlalchemyMediaAssetRepository(db_session)
    asset = _new_asset().mark_scanned_clean(now=NOW)
    await repo.add(asset)
    await db_session.flush()
    processed = asset.complete_processing(variants=(_variant(asset),), now=NOW)
    await repo.save(processed)
    await db_session.flush()

    await repo.delete(asset.id)
    await db_session.flush()

    assert await repo.get_by_id(asset.id) is None
    result = await db_session.execute(
        select(ImageVariantRow).where(ImageVariantRow.media_asset_id == asset.id.value)
    )
    assert result.scalars().all() == []


async def test_storage_key_uniqueness_is_enforced(db_session: AsyncSession) -> None:
    repo = SqlalchemyMediaAssetRepository(db_session)
    asset_a = _new_asset()
    asset_b = _new_asset()
    object.__setattr__(asset_b, "storage_key", asset_a.storage_key)  # force a collision
    await repo.add(asset_a)
    await db_session.flush()

    # `add()` flushes internally (parent-before-children row ordering, same convention as
    # every other repository's `add()` in this codebase) -- the unique-constraint violation is
    # therefore raised by this call itself, not by a later explicit flush.
    with pytest.raises(IntegrityError):
        await repo.add(asset_b)
    await db_session.rollback()  # required after a caught flush error before reusing the session


async def test_list_pending_scan_only_returns_pending_scan_status(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyMediaAssetRepository(db_session)
    pending = _new_asset()
    clean = _new_asset().mark_scanned_clean(now=NOW)
    await repo.add(pending)
    await repo.add(clean)
    await db_session.flush()

    results = await repo.list_pending_scan(limit=10)
    assert {a.id.value for a in results} == {pending.id.value}


async def test_list_pending_processing_only_returns_clean_and_pending_processing(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyMediaAssetRepository(db_session)
    not_scanned = _new_asset()
    clean_pending = _new_asset().mark_scanned_clean(now=NOW)
    await repo.add(not_scanned)
    await repo.add(clean_pending)
    await db_session.flush()

    results = await repo.list_pending_processing(limit=10)
    assert {a.id.value for a in results} == {clean_pending.id.value}
