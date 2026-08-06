"""Shared fixtures for `ads`'s fast (no-DB) unit + API tests: in-memory fakes for every port
`application/ports.py` declares, mirroring `apps/backend/tests/billing/conftest.py`'s pattern
exactly.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from ads.application.ports import EntitlementSnapshot, SlotSnapshot
from ads.domain import BannerCampaign, CreativeStatus, Schedule, Targeting
from shared_kernel import EventEnvelope


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id)


@dataclass
class FakeBannerCampaignRepository:
    """Implements `ads.application.ports.BannerCampaignRepository`."""

    campaigns: dict[UUID, BannerCampaign] = field(default_factory=dict)

    async def get_by_id(self, campaign_id: UUID) -> BannerCampaign | None:
        return self.campaigns.get(campaign_id)

    async def add(self, campaign: BannerCampaign) -> None:
        self.campaigns[campaign.id] = campaign

    async def save(self, campaign: BannerCampaign) -> BannerCampaign:
        self.campaigns[campaign.id] = campaign
        return campaign

    async def list_for_operator(
        self,
        *,
        status: object | None,
        slot_key: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[BannerCampaign], str | None]:
        items = sorted(self.campaigns.values(), key=lambda c: (c.created_at, c.id))
        if status is not None:
            items = [c for c in items if c.status == status]
        if slot_key is not None:
            items = [c for c in items if c.slot_key == slot_key]
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            items = [i for i in items if (i.created_at, i.id) > (created_at, row_id)]
        page = items[: limit + 1]
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = _encode_cursor(page[-1].created_at, page[-1].id)
        return page, next_cursor

    async def list_candidates_for_serve(self, *, slot_key: str) -> tuple[BannerCampaign, ...]:
        candidates = [
            c
            for c in self.campaigns.values()
            if c.slot_key == slot_key and c.status.value in ("SCHEDULED", "RUNNING")
        ]
        candidates.sort(key=lambda c: (-c.schedule.priority, c.created_at))
        return tuple(candidates)

    async def list_by_creative_media_asset_id(
        self, media_asset_id: UUID
    ) -> tuple[BannerCampaign, ...]:
        return tuple(
            c for c in self.campaigns.values() if c.creative_media_asset_id == media_asset_id
        )

    async def list_due_to_start(self, *, now: datetime) -> tuple[BannerCampaign, ...]:
        return tuple(
            c
            for c in self.campaigns.values()
            if c.status.value == "SCHEDULED" and c.schedule.start <= now
        )

    async def list_due_to_end(self, *, now: datetime) -> tuple[BannerCampaign, ...]:
        return tuple(
            c
            for c in self.campaigns.values()
            if c.status.value in ("SCHEDULED", "RUNNING", "PAUSED") and c.schedule.end <= now
        )


@dataclass
class FakeEntitlementProjectionRepository:
    """Implements `ads.application.ports.EntitlementProjectionRepository`."""

    entitlements: dict[UUID, EntitlementSnapshot] = field(default_factory=dict)

    async def get_by_id(self, entitlement_id: UUID) -> EntitlementSnapshot | None:
        return self.entitlements.get(entitlement_id)

    async def upsert(self, snapshot: EntitlementSnapshot) -> None:
        self.entitlements[snapshot.entitlement_id] = snapshot

    async def mark_state(self, entitlement_id: UUID, *, activation_state: str) -> None:
        existing = self.entitlements.get(entitlement_id)
        if existing is None:
            return
        self.entitlements[entitlement_id] = EntitlementSnapshot(
            entitlement_id=existing.entitlement_id,
            target_id=existing.target_id,
            valid_from=existing.valid_from,
            valid_until=existing.valid_until,
            activation_state=activation_state,
        )


class FakePlacementSlotReaderPort:
    """Implements `ads.application.ports.PlacementSlotReaderPort`."""

    def __init__(self) -> None:
        self.slots: dict[str, SlotSnapshot] = {}

    def seed(self, slot_key: str = "HOMEPAGE_TOP") -> SlotSnapshot:
        snapshot = SlotSnapshot(head_id=uuid4(), version_id=uuid4(), slot_key=slot_key)
        self.slots[slot_key] = snapshot
        return snapshot

    async def get_slot_by_key(self, slot_key: str) -> SlotSnapshot | None:
        return self.slots.get(slot_key)


class FakeCreativeReaderPort:
    """Implements `ads.application.ports.CreativeReaderPort`."""

    def __init__(self) -> None:
        self.statuses: dict[UUID, CreativeStatus] = {}
        self.default_status = CreativeStatus.CLEAN

    async def get_creative_status(self, media_asset_id: UUID) -> CreativeStatus:
        return self.statuses.get(media_asset_id, self.default_status)


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


@pytest.fixture
def fake_campaigns() -> FakeBannerCampaignRepository:
    return FakeBannerCampaignRepository()


@pytest.fixture
def fake_entitlement_projection() -> FakeEntitlementProjectionRepository:
    return FakeEntitlementProjectionRepository()


@pytest.fixture
def fake_slots() -> FakePlacementSlotReaderPort:
    return FakePlacementSlotReaderPort()


@pytest.fixture
def fake_creatives() -> FakeCreativeReaderPort:
    return FakeCreativeReaderPort()


@pytest.fixture
def fake_outbox() -> FakeOutbox:
    return FakeOutbox()


def make_schedule(*, start: datetime, end: datetime, priority: int = 0) -> Schedule:
    return Schedule(start=start, end=end, priority=priority)


def make_targeting(**kwargs: object) -> Targeting:
    return Targeting(**kwargs)  # type: ignore[arg-type]
