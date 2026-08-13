"""Shared fixtures for `profiles`' fast (no-DB) unit + API tests: in-memory fakes for every port
`application/ports.py` declares, mirroring the real adapters' query semantics closely enough to
exercise use-case behaviour without a real database. Mirrors `apps/backend/tests/catalog/
conftest.py`'s pattern exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

import pytest

from profiles.application.ports import (
    MediaAssetSnapshot,
    VerificationEligibilitySnapshot,
)
from profiles.domain import BusinessProfile, CaseStatus, ProfileType, VerificationCase
from shared_kernel import BusinessProfileId, EventEnvelope, UserId


@dataclass
class FakeBusinessProfileRepository:
    profiles: dict[UUID, BusinessProfile] = field(default_factory=dict)

    async def get_by_id(self, profile_id: BusinessProfileId) -> BusinessProfile | None:
        return self.profiles.get(profile_id.value)

    async def add(self, profile: BusinessProfile) -> None:
        self.profiles[profile.id.value] = profile

    async def save(self, profile: BusinessProfile) -> BusinessProfile:
        self.profiles[profile.id.value] = profile
        return profile

    async def list_by_owner(
        self, owner_user_id: UserId, *, cursor: str | None, limit: int
    ) -> tuple[list[BusinessProfile], str | None]:
        items = [p for p in self.profiles.values() if p.owner_user_id == owner_user_id]
        items.sort(key=lambda p: p.created_at)
        return items[:limit], None

    async def list_public(
        self,
        *,
        profile_type: ProfileType | None,
        verified_only: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[BusinessProfile], str | None]:
        items = [p for p in self.profiles.values() if p.status.value != "ARCHIVED"]
        if profile_type is not None:
            items = [p for p in items if p.profile_type == profile_type]
        if verified_only:
            items = [p for p in items if p.badge is not None and p.badge.status.value == "VALID"]
        items.sort(key=lambda p: p.created_at)
        return items[:limit], None

    async def list_admin(
        self, *, status: str | None, cursor: str | None, limit: int
    ) -> tuple[list[BusinessProfile], str | None]:
        items = list(self.profiles.values())
        if status is not None:
            items = [p for p in items if p.status.value == status]
        items.sort(key=lambda p: p.created_at)
        return items[:limit], None

    async def count_all(self) -> int:
        return len(self.profiles)

    async def get_by_portfolio_media_asset_id(self, media_asset_id: UUID) -> BusinessProfile | None:
        for profile in self.profiles.values():
            if any(item.media_asset_id == media_asset_id for item in profile.portfolio):
                return profile
        return None

    async def list_badges_expiring(self, *, now: datetime, limit: int) -> list[BusinessProfile]:
        items = [
            p
            for p in self.profiles.values()
            if p.badge is not None
            and p.badge.status.value == "VALID"
            and p.badge.valid_until <= now
        ]
        items.sort(key=lambda p: p.badge.valid_until)  # type: ignore[union-attr]
        return items[:limit]


@dataclass
class FakeVerificationCaseRepository:
    cases: dict[UUID, VerificationCase] = field(default_factory=dict)

    async def get_by_id(self, case_id: UUID) -> VerificationCase | None:
        return self.cases.get(case_id)

    async def get_current_for_profile(
        self, profile_id: BusinessProfileId
    ) -> VerificationCase | None:
        items = [c for c in self.cases.values() if c.business_profile_id == profile_id]
        items.sort(key=lambda c: c.created_at, reverse=True)
        return items[0] if items else None

    async def add(self, case: VerificationCase) -> None:
        self.cases[case.id] = case

    async def save(self, case: VerificationCase) -> VerificationCase:
        self.cases[case.id] = case
        return case

    async def list_queue(
        self, *, status: CaseStatus | None, cursor: str | None, limit: int
    ) -> tuple[list[VerificationCase], str | None]:
        items = list(self.cases.values())
        if status is not None:
            items = [c for c in items if c.status == status]
        items.sort(key=lambda c: c.sla_due_at)
        return items[:limit], None

    async def get_by_document_media_asset_id(self, media_asset_id: UUID) -> VerificationCase | None:
        for case in self.cases.values():
            if any(document.media_asset_id == media_asset_id for document in case.documents):
                return case
        return None


@dataclass
class FakeVerificationEligibilityRepository:
    snapshots: dict[UUID, VerificationEligibilitySnapshot] = field(default_factory=dict)
    """Keyed by entitlement_id, mirroring the real repository."""

    async def get_active_for_profile(
        self, profile_id: BusinessProfileId, *, now: datetime
    ) -> VerificationEligibilitySnapshot | None:
        candidates = [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.business_profile_id == profile_id
            and snapshot.activation_state == "ACTIVE"
            and snapshot.valid_until > now
        ]
        candidates.sort(key=lambda snapshot: snapshot.valid_until, reverse=True)
        return candidates[0] if candidates else None

    async def get_by_entitlement_id(
        self, entitlement_id: UUID
    ) -> VerificationEligibilitySnapshot | None:
        return self.snapshots.get(entitlement_id)

    async def upsert(self, snapshot: VerificationEligibilitySnapshot) -> None:
        self.snapshots[snapshot.entitlement_id] = snapshot


class FakeMediaAssetReaderPort:
    def __init__(self) -> None:
        self.assets: dict[UUID, MediaAssetSnapshot] = {}

    def seed(
        self,
        media_asset_id: UUID,
        *,
        scan_status: Literal["PENDING", "CLEAN", "QUARANTINED"] = "CLEAN",
    ) -> None:
        self.assets[media_asset_id] = MediaAssetSnapshot(id=media_asset_id, scan_status=scan_status)

    async def get_media_asset(self, media_asset_id: UUID) -> MediaAssetSnapshot | None:
        return self.assets.get(media_asset_id)


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


@pytest.fixture
def fake_profiles() -> FakeBusinessProfileRepository:
    return FakeBusinessProfileRepository()


@pytest.fixture
def fake_cases() -> FakeVerificationCaseRepository:
    return FakeVerificationCaseRepository()


@pytest.fixture
def fake_eligibility() -> FakeVerificationEligibilityRepository:
    return FakeVerificationEligibilityRepository()


@pytest.fixture
def fake_media() -> FakeMediaAssetReaderPort:
    return FakeMediaAssetReaderPort()


@pytest.fixture
def fake_outbox() -> FakeOutbox:
    return FakeOutbox()
