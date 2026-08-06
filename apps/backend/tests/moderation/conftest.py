"""Shared fixtures for `moderation`'s fast (no-DB) unit + API tests: in-memory fakes for every
port `application/ports.py` declares -- including the three narrow command-target Protocols
(`ListingModerationCommandPort`/`AccountSuspensionCommandPort`/`ProfileModerationCommandPort`)
moderation's own `ModerationActionService` dispatches to, recorded here as call logs so tests can
assert exactly one command reached exactly the right target with the right arguments (the
"interface-only-action" guarantee). Mirrors `apps/backend/tests/profiles/conftest.py`'s pattern
exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from moderation.application.action_service import ModerationActionService
from moderation.domain import CaseStatus, ModerationCase, SubjectType
from shared_kernel import EventEnvelope


@dataclass
class FakeModerationCaseRepository:
    cases: dict[UUID, ModerationCase] = field(default_factory=dict)

    async def get_by_id(self, case_id: UUID) -> ModerationCase | None:
        return self.cases.get(case_id)

    async def get_open_or_in_review_for_subject(
        self, subject_type: SubjectType, subject_id: UUID
    ) -> ModerationCase | None:
        candidates = [
            c
            for c in self.cases.values()
            if c.subject.subject_type == subject_type
            and c.subject.subject_id == subject_id
            and c.status in (CaseStatus.OPEN, CaseStatus.IN_REVIEW)
        ]
        return candidates[0] if candidates else None

    async def add(self, case: ModerationCase) -> None:
        self.cases[case.id] = case

    async def save(self, case: ModerationCase) -> ModerationCase:
        self.cases[case.id] = case
        return case

    async def list_queue(
        self,
        *,
        status: CaseStatus | None,
        subject_type: SubjectType | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ModerationCase], str | None]:
        items = list(self.cases.values())
        if status is not None:
            items = [c for c in items if c.status == status]
        if subject_type is not None:
            items = [c for c in items if c.subject.subject_type == subject_type]
        items.sort(key=lambda c: c.created_at)
        return items[:limit], None


@dataclass
class FakeListingModerationCommandPort:
    calls: list[tuple[str, UUID, UUID | None, str | None]] = field(default_factory=list)
    """(method_name, listing_id, moderator_user_id, reason) -- `moderator_user_id` is `None` for
    `unflag_listing` (that method carries no moderator argument)."""

    async def hide_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        self.calls.append(("hide_listing", listing_id, moderator_user_id, reason))

    async def reject_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        self.calls.append(("reject_listing", listing_id, moderator_user_id, reason))

    async def suspend_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        self.calls.append(("suspend_listing", listing_id, moderator_user_id, reason))

    async def remove_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        self.calls.append(("remove_listing", listing_id, moderator_user_id, reason))

    async def unflag_listing(self, listing_id: UUID, *, reason: str | None) -> None:
        self.calls.append(("unflag_listing", listing_id, None, reason))


@dataclass
class FakeAccountSuspensionCommandPort:
    calls: list[tuple[UUID, str | None]] = field(default_factory=list)

    async def suspend_account(self, account_id: UUID, *, reason: str | None) -> None:
        self.calls.append((account_id, reason))


@dataclass
class FakeProfileModerationCommandPort:
    revoke_calls: list[UUID] = field(default_factory=list)
    archive_calls: list[UUID] = field(default_factory=list)

    async def revoke_badge(self, profile_id: UUID) -> None:
        self.revoke_calls.append(profile_id)

    async def archive_profile(self, profile_id: UUID) -> None:
        self.archive_calls.append(profile_id)


class FakeOutbox:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


@pytest.fixture
def fake_cases() -> FakeModerationCaseRepository:
    return FakeModerationCaseRepository()


@pytest.fixture
def fake_listings() -> FakeListingModerationCommandPort:
    return FakeListingModerationCommandPort()


@pytest.fixture
def fake_accounts() -> FakeAccountSuspensionCommandPort:
    return FakeAccountSuspensionCommandPort()


@pytest.fixture
def fake_profiles() -> FakeProfileModerationCommandPort:
    return FakeProfileModerationCommandPort()


@pytest.fixture
def fake_outbox() -> FakeOutbox:
    return FakeOutbox()


@pytest.fixture
def action_service(
    fake_listings: FakeListingModerationCommandPort,
    fake_accounts: FakeAccountSuspensionCommandPort,
    fake_profiles: FakeProfileModerationCommandPort,
) -> ModerationActionService:
    return ModerationActionService(
        listings=fake_listings, accounts=fake_accounts, profiles=fake_profiles
    )
