"""Degradation proof: media processing lag never blocks listing publish. `catalog.application.
listing_use_cases.ListingUseCases._attach_verified_image` performs an EXISTENCE-only check
against `MediaAssetReaderPort.get_media_asset` (its own docstring: "no sanctioned way to verify
the caller uploaded this specific asset" -- it never inspects `scan_status`), and `Listing.
publish` (`catalog/domain/listing.py`) never reads `self.images` at all -- so a listing can attach
an image whose underlying media asset is still `scan_status="PENDING"` (virus scan / thumbnail
generation not yet finished by media's own async pipeline) and publish successfully regardless.
Proves this against the REAL `ListingUseCases`/`Listing` aggregate/Postgres repository, not by
asserting the absence of a call in the source -- if a future change adds a scan-status gate to
either method, this test starts failing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from catalog.application import ListingUseCases
from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.ports import CatalogPlatformSettings, MediaAssetSnapshot
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ImageStatus, LifecycleState, ListingType
from catalog.infrastructure.persistence.base import CatalogBase
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.infrastructure.persistence.repository import (
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from shared_kernel import BusinessProfileId, ListingId, UserId
from tests.integration.conftest import ensure_clean_schema

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _catalog_schema(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "catalog", CatalogBase)


class _UnusedCategoryFormPort:
    async def get_category(self, category_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def get_current_form_binding(self, category_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _FixedPlatformSettingsReaderPort:
    async def get_catalog_settings(self) -> CatalogPlatformSettings:
        return CatalogPlatformSettings(default_expiry_days=30)


class _StillScanningMediaAssetReaderPort:
    """Mimics media's own pipeline mid-lag: the asset row exists (upload succeeded) but virus
    scan / thumbnail generation has not finished -- `scan_status` is still `"PENDING"`, exactly
    what `media.infrastructure`'s real intake pipeline reports before its async worker catches
    up."""

    def __init__(self, media_asset_id: UUID) -> None:
        self._media_asset_id = media_asset_id

    async def get_media_asset(self, media_asset_id: UUID) -> MediaAssetSnapshot | None:
        if media_asset_id != self._media_asset_id:
            return None
        return MediaAssetSnapshot(id=media_asset_id, scan_status="PENDING")


class _UnusedCreditBalancePort:
    async def consume_one_listing_credit(self, *, owner_profile_id: BusinessProfileId) -> NoReturn:
        raise AssertionError("not exercised by this test")


async def test_attaching_a_still_scanning_image_does_not_block_publish(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_id = UserId(value=uuid4())
    media_asset_id = uuid4()
    listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=owner_id,
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/x",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="Listing with a still-scanning image",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="listing-with-a-still-scanning-image",
        now=NOW,
    )

    async with session_factory() as session:
        listings_repo = SqlalchemyListingRepository(session)
        await listings_repo.add(listing)
        use_cases = ListingUseCases(
            listings=listings_repo,
            categories=_UnusedCategoryFormPort(),
            settings=_FixedPlatformSettingsReaderPort(),
            media=_StillScanningMediaAssetReaderPort(media_asset_id),
            outbox=OutboxWriter(session, CatalogOutboxEventRow),
            quota=QuotaEnforcementService(
                subscriptions=SqlalchemySubscriptionSnapshotRepository(session)
            ),
            duplicates=DuplicateDetectionService(listings=listings_repo),
            credit_balance=_UnusedCreditBalancePort(),
        )
        attachment = await use_cases.attach_image(
            listing_id=listing.id,
            actor_user_id=owner_id,
            media_asset_id=media_asset_id,
            now=NOW,
        )
        assert attachment.status is ImageStatus.PENDING

        published = await use_cases.publish_listing(
            listing_id=listing.id,
            actor_user_id=owner_id,
            now=NOW + timedelta(minutes=1),
        )

    assert published.lifecycle_state is LifecycleState.PUBLISHED
    assert published.images[-1].status is ImageStatus.PENDING, (
        "the image's scan status is still lagging behind -- publish must not have waited for it"
    )
