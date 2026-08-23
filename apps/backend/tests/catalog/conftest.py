"""Shared fixtures for `catalog`'s fast (no-DB) unit + API tests: in-memory fakes for every port
`application/ports.py` declares, mirroring the real adapters' query semantics closely enough to
exercise use-case behaviour without a real database. Mirrors `apps/backend/tests/media/conftest.py`'s
pattern exactly."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

import pytest

from catalog.application.ports import (
    CatalogPlatformSettings,
    CategorySnapshot,
    FormBinding,
    MediaAssetSnapshot,
    SubscriptionSnapshot,
)
from catalog.domain import Favorite, FieldValidatorSpec, Listing
from shared_kernel import BusinessProfileId, EventEnvelope, ListingId, UserId


@dataclass
class FakeListingRepository:
    """Implements `catalog.application.ports.ListingRepository`."""

    listings: dict[UUID, Listing] = field(default_factory=dict)

    async def get_by_id(self, listing_id: ListingId) -> Listing | None:
        return self.listings.get(listing_id.value)

    async def add(self, listing: Listing) -> None:
        self.listings[listing.id.value] = listing

    async def save(self, listing: Listing) -> Listing:
        self.listings[listing.id.value] = listing
        return listing

    async def get_by_image_media_asset_id(self, media_asset_id: UUID) -> Listing | None:
        for listing in self.listings.values():
            if any(image.media_asset_id == media_asset_id for image in listing.images):
                return listing
        return None

    async def list_by_owner(
        self,
        owner_user_id: UserId,
        *,
        state: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Listing], str | None]:
        items = [
            item
            for item in self.listings.values()
            if item.owner_user_id == owner_user_id
        ]
        if state is not None:
            items = [item for item in items if item.lifecycle_state.value == state]
        items.sort(key=lambda item: item.created_at)
        return items[:limit], None

    async def list_by_owner_profile(
        self,
        owner_profile_id: BusinessProfileId,
        *,
        state: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Listing], str | None]:
        items = [
            item
            for item in self.listings.values()
            if item.owner_profile_id == owner_profile_id
        ]
        if state is not None:
            items = [item for item in items if item.lifecycle_state.value == state]
        items.sort(key=lambda item: item.created_at)
        return items[:limit], None

    async def list_public(
        self,
        *,
        category_id: UUID | None,
        listing_type: str | None,
        cursor: str | None,
        limit: int,
        now: datetime,
    ) -> tuple[list[Listing], str | None]:
        items = [
            item for item in self.listings.values() if item.is_publicly_visible(now=now)
        ]
        if category_id is not None:
            items = [item for item in items if item.category_id == category_id]
        if listing_type is not None:
            items = [item for item in items if item.listing_type.value == listing_type]
        items.sort(key=lambda item: item.created_at)
        return items[:limit], None

    async def list_expiring(self, *, now: datetime, limit: int) -> list[Listing]:
        items = [
            item
            for item in self.listings.values()
            if item.lifecycle_state.value in ("PUBLISHED", "EDITED")
            and item.expires_at is not None
            and item.expires_at <= now
        ]
        return items[:limit]

    async def count_active_by_owner_profile(
        self, owner_profile_id: BusinessProfileId
    ) -> int:
        return sum(
            1
            for item in self.listings.values()
            if item.owner_profile_id == owner_profile_id
            and item.lifecycle_state.value != "DELETED"
        )

    async def find_recent_by_owner_category(
        self,
        *,
        owner_user_id: UserId,
        category_id: UUID,
        exclude_listing_id: ListingId | None,
        limit: int,
    ) -> list[Listing]:
        items = [
            item
            for item in self.listings.values()
            if item.owner_user_id == owner_user_id
            and item.category_id == category_id
            and (exclude_listing_id is None or item.id != exclude_listing_id)
        ]
        return items[:limit]


@dataclass
class FakeFavoriteRepository:
    """Implements `catalog.application.ports.FavoriteRepository`."""

    rows: dict[tuple[UUID, UUID], Favorite] = field(default_factory=dict)

    async def get(self, *, user_id: UserId, listing_id: ListingId) -> Favorite | None:
        return self.rows.get((user_id.value, listing_id.value))

    async def add(self, favorite: Favorite) -> None:
        self.rows[(favorite.user_id.value, favorite.listing_id.value)] = favorite

    async def delete(self, *, user_id: UserId, listing_id: ListingId) -> None:
        self.rows.pop((user_id.value, listing_id.value), None)

    async def list_for_user(
        self, user_id: UserId, *, cursor: str | None, limit: int
    ) -> tuple[list[Favorite], str | None]:
        items = [f for (u, _), f in self.rows.items() if u == user_id.value]
        return items[:limit], None

    async def count_for_listing(self, listing_id: ListingId) -> int:
        return sum(1 for (_, item), _f in self.rows.items() if item == listing_id.value)


class FakeCategoryFormPort:
    """Implements `catalog.application.ports.CategoryFormPort`. `specs` defaults to a single
    required `numeric_range` field ("rooms", 1-10) plus an `image_count` cap of 10; tests override
    via `category.specs = (...)` for other shapes."""

    def __init__(self) -> None:
        self.category_status: dict[UUID, Literal["ACTIVE", "RETIRED"]] = {}
        self.form_definition_id: UUID | None = None
        self.form_definition_version_id: UUID | None = None
        self.specs: tuple[FieldValidatorSpec, ...] = (
            FieldValidatorSpec(
                field_code="rooms",
                validator_type="numeric_range",
                params={"min": 1, "max": 10},
                required_field=True,
            ),
        )
        self.category_path = "/real-estate/apartments"
        self.form_binding_available = True
        # UNF-020: `None` skips the unknown-field check entirely (matches `validate_attribute_
        # set`'s own opt-in default), so the many existing tests that don't care about this
        # invariant keep submitting whatever attribute shape they already do. Tests that DO care
        # set this explicitly (a real binding's `field_codes` always come from the actual form,
        # never `None`).
        self.field_codes: frozenset[str] | None = None

    async def get_category(self, category_id: UUID) -> CategorySnapshot | None:
        status = self.category_status.get(category_id, "ACTIVE")
        return CategorySnapshot(
            id=category_id,
            path=self.category_path,
            status=status,
            form_definition_head_id=None,
        )

    async def get_current_form_binding(self, category_id: UUID) -> FormBinding | None:
        if not self.form_binding_available:
            return None
        return FormBinding(
            form_definition_id=self.form_definition_id or UUID(int=1),
            form_definition_version_id=self.form_definition_version_id or UUID(int=2),
            specs=self.specs,
            field_codes=self.field_codes,
        )


class FakePlatformSettingsReaderPort:
    def __init__(self, *, default_expiry_days: int = 30) -> None:
        self.default_expiry_days = default_expiry_days

    async def get_catalog_settings(self) -> CatalogPlatformSettings:
        return CatalogPlatformSettings(default_expiry_days=self.default_expiry_days)


class FakeMediaAssetReaderPort:
    def __init__(self) -> None:
        self.assets: dict[UUID, MediaAssetSnapshot] = {}

    def seed(
        self,
        media_asset_id: UUID,
        *,
        scan_status: Literal["PENDING", "CLEAN", "QUARANTINED"] = "PENDING",
    ) -> None:
        self.assets[media_asset_id] = MediaAssetSnapshot(
            id=media_asset_id, scan_status=scan_status
        )

    async def get_media_asset(self, media_asset_id: UUID) -> MediaAssetSnapshot | None:
        return self.assets.get(media_asset_id)


@dataclass
class FakeSubscriptionSnapshotRepository:
    snapshots: dict[UUID, SubscriptionSnapshot] = field(default_factory=dict)

    async def get_for_profile(
        self, owner_profile_id: BusinessProfileId
    ) -> SubscriptionSnapshot | None:
        return self.snapshots.get(owner_profile_id.value)

    async def upsert(self, snapshot: SubscriptionSnapshot) -> None:
        self.snapshots[snapshot.owner_profile_id.value] = snapshot


@dataclass
class FakeCreditBalancePort:
    """Implements `catalog.application.ports.CreditBalancePort` (listing paywall Phase 4,
    2026-08-23). `has_credit` is a simple test knob (real billing-side eligibility logic is
    billing's own, exercised in `apps/backend/tests/billing/`) -- `consumed_for` records every
    profile a credit was actually spent for, so a test can assert consumption happened exactly
    once, not merely that a credit existed."""

    has_credit: bool = False
    consumed_for: list[UUID] = field(default_factory=list)

    async def consume_one_listing_credit(
        self, *, owner_profile_id: BusinessProfileId
    ) -> bool:
        if not self.has_credit:
            return False
        self.consumed_for.append(owner_profile_id.value)
        return True


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


@pytest.fixture
def fake_listings() -> FakeListingRepository:
    return FakeListingRepository()


@pytest.fixture
def fake_favorites() -> FakeFavoriteRepository:
    return FakeFavoriteRepository()


@pytest.fixture
def fake_categories() -> FakeCategoryFormPort:
    return FakeCategoryFormPort()


@pytest.fixture
def fake_settings() -> FakePlatformSettingsReaderPort:
    return FakePlatformSettingsReaderPort()


@pytest.fixture
def fake_media() -> FakeMediaAssetReaderPort:
    return FakeMediaAssetReaderPort()


@pytest.fixture
def fake_subscriptions() -> FakeSubscriptionSnapshotRepository:
    return FakeSubscriptionSnapshotRepository()


@pytest.fixture
def fake_credit_balance() -> FakeCreditBalancePort:
    return FakeCreditBalancePort()


@pytest.fixture
def fake_outbox() -> FakeOutbox:
    return FakeOutbox()
