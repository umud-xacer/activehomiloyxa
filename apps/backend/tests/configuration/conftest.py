"""Shared fixtures for `configuration`'s fast (no-DB) unit + API tests: in-memory fakes for the
three ports `application/ports.py` declares (`ConfigHeadRepository`, `SnapshotCachePort`) plus
`shared_kernel.OutboxPort`, mirroring `SqlalchemyConfigHeadRepository`'s query semantics closely
enough to exercise the gate's dependency/cycle checks without a real database. Real-Postgres/
Redis integration tests live under `integration/` with their own `conftest.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from configuration.application.category_read import CategoryReadUseCases
from configuration.application.use_cases import ConfigurationUseCases
from configuration.domain import ConfigEntityType, ConfigHead, ConfigVersion
from shared_kernel import EventEnvelope


@dataclass
class FakeConfigHeadRepository:
    """In-memory stand-in for `SqlalchemyConfigHeadRepository`, replicating its query logic
    (ancestor-chain walk, dependency-existence rule: "publishable" = has a current version) so
    gate-context-dependent tests (cycles, missing dependencies) behave the same as against real
    Postgres."""

    heads: dict[tuple[ConfigEntityType, UUID], ConfigHead] = field(default_factory=dict)
    versions: dict[tuple[ConfigEntityType, UUID], ConfigVersion] = field(default_factory=dict)
    permission_groups: dict[str, frozenset[str]] = field(default_factory=dict)
    bound_listings: dict[UUID, bool] = field(default_factory=dict)

    async def get_head(self, entity_type: ConfigEntityType, head_id: UUID) -> ConfigHead | None:
        return self.heads.get((entity_type, head_id))

    async def get_head_by_code(self, entity_type: ConfigEntityType, code: str) -> ConfigHead | None:
        for (et, _), head in self.heads.items():
            if et is entity_type and head.code == code:
                return head
        return None

    async def list_heads(
        self, entity_type: ConfigEntityType, *, cursor: str | None, limit: int
    ) -> tuple[list[ConfigHead], str | None]:
        items = sorted(
            (h for (et, _), h in self.heads.items() if et is entity_type),
            key=lambda h: (h.created_at, str(h.id)),
        )
        page = items[:limit]
        next_cursor = "more" if len(items) > limit else None
        return page, next_cursor

    async def list_versions(
        self, entity_type: ConfigEntityType, head_id: UUID
    ) -> list[ConfigVersion]:
        return sorted(
            (
                v
                for (et, _), v in self.versions.items()
                if et is entity_type and v.head_id == head_id
            ),
            key=lambda v: v.version_number,
        )

    async def get_version(
        self, entity_type: ConfigEntityType, head_id: UUID, version_id: UUID
    ) -> ConfigVersion | None:
        version = self.versions.get((entity_type, version_id))
        if version is not None and version.head_id == head_id:
            return version
        return None

    async def latest_version_number(self, entity_type: ConfigEntityType, head_id: UUID) -> int:
        numbers = [
            v.version_number
            for (et, _), v in self.versions.items()
            if et is entity_type and v.head_id == head_id
        ]
        return max(numbers) if numbers else 0

    async def add_head(self, entity_type: ConfigEntityType, head: ConfigHead) -> None:
        self.heads[(entity_type, head.id)] = head

    async def add_version(self, entity_type: ConfigEntityType, version: ConfigVersion) -> None:
        self.versions[(entity_type, version.id)] = version

    async def update_version(self, entity_type: ConfigEntityType, version: ConfigVersion) -> None:
        self.versions[(entity_type, version.id)] = version

    async def update_head(self, entity_type: ConfigEntityType, head: ConfigHead) -> None:
        self.heads[(entity_type, head.id)] = head

    async def existing_codes(
        self, entity_type: ConfigEntityType, *, exclude_head_id: UUID | None
    ) -> frozenset[str]:
        return frozenset(
            h.code
            for (et, hid), h in self.heads.items()
            if et is entity_type and hid != exclude_head_id
        )

    async def dependency_exists(self, kind: str, reference: str) -> bool:
        if kind == "permission-group":
            return reference in self.permission_groups
        try:
            entity_type = ConfigEntityType(kind)
        except ValueError:
            return False
        try:
            ref_uuid = UUID(reference)
        except ValueError:
            head = await self.get_head_by_code(entity_type, reference)
        else:
            head = await self.get_head(entity_type, ref_uuid)
        return head is not None and head.current_version_id is not None

    async def category_has_bound_listings(self, category_head_id: UUID) -> bool:
        return self.bound_listings.get(category_head_id, False)

    async def ancestor_codes(self, entity_type: ConfigEntityType, of_code: str) -> frozenset[str]:
        head = await self.get_head_by_code(entity_type, of_code)
        if head is None or head.current_version_id is None:
            return frozenset()
        version = await self.get_version(entity_type, head.id, head.current_version_id)
        if version is None:
            return frozenset()

        parent_field = (
            "parent_category_id" if entity_type is ConfigEntityType.CATEGORY else "parent_role_code"
        )
        parent_ref = version.definition_document.get(parent_field)
        if not parent_ref:
            return frozenset({of_code})

        if entity_type is ConfigEntityType.CATEGORY:
            parent_head = await self.get_head(entity_type, UUID(str(parent_ref)))
            parent_code = parent_head.code if parent_head is not None else None
        else:
            parent_code = str(parent_ref)

        if parent_code is None:
            return frozenset({of_code})
        return frozenset({of_code}) | await self.ancestor_codes(entity_type, parent_code)

    async def permission_group_keys(self, codes: list[str]) -> dict[str, frozenset[str]]:
        return {c: self.permission_groups[c] for c in codes if c in self.permission_groups}

    async def role_flattened_permission_keys(self, role_code: str) -> frozenset[str]:
        head = await self.get_head_by_code(ConfigEntityType.ROLE_DEFINITION, role_code)
        if head is None or head.current_version_id is None:
            return frozenset()
        version = await self.get_version(
            ConfigEntityType.ROLE_DEFINITION, head.id, head.current_version_id
        )
        if version is None:
            return frozenset()
        return frozenset(version.definition_document.get("permission_keys", []))

    async def conflicting_active_version_exists(
        self,
        entity_type: ConfigEntityType,
        head_id: UUID,
        *,
        validity_from: object,
        validity_until: object,
    ) -> bool:
        return False


@dataclass
class FakeSnapshotCache:
    store: dict[tuple[ConfigEntityType, str], dict[str, Any]] = field(default_factory=dict)

    async def put(self, entity_type: ConfigEntityType, code: str, snapshot: dict[str, Any]) -> None:
        self.store[(entity_type, code)] = snapshot

    async def get(self, entity_type: ConfigEntityType, code: str) -> dict[str, Any] | None:
        return self.store.get((entity_type, code))

    async def invalidate(self, entity_type: ConfigEntityType, code: str) -> None:
        self.store.pop((entity_type, code), None)

    async def list_current(self, entity_type: ConfigEntityType) -> list[dict[str, Any]]:
        return [v for (et, _), v in self.store.items() if et is entity_type]


@dataclass
class FakeOutbox:
    events: list[EventEnvelope] = field(default_factory=list)

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


@dataclass
class FakeOwnerAdminLockoutCounter:
    """In-memory stand-in for `OwnerAdminLockoutPort` (`RedisOwnerAdminLockoutCounter` in
    production) -- an in-memory `{identifier: count}` map, mirroring `identity`'s own
    `FakeLoginAttemptTracker` (`identity/tests/conftest.py`)."""

    counts: dict[str, int] = field(default_factory=dict)

    async def record_failure(self, *, identifier: str, window_seconds: int) -> int:
        self.counts[identifier] = self.counts.get(identifier, 0) + 1
        return self.counts[identifier]

    async def get_failure_count(self, *, identifier: str) -> int:
        return self.counts.get(identifier, 0)

    async def get_retry_after_seconds(self, *, identifier: str) -> int:
        return 900 if self.counts.get(identifier, 0) > 0 else 0

    async def reset(self, *, identifier: str) -> None:
        self.counts.pop(identifier, None)


@pytest.fixture
def fake_repo() -> FakeConfigHeadRepository:
    return FakeConfigHeadRepository()


@pytest.fixture
def fake_cache() -> FakeSnapshotCache:
    return FakeSnapshotCache()


@pytest.fixture
def fake_outbox() -> FakeOutbox:
    return FakeOutbox()


@pytest.fixture
def fake_owner_admin_lockout() -> FakeOwnerAdminLockoutCounter:
    return FakeOwnerAdminLockoutCounter()


@pytest.fixture
def use_cases(
    fake_repo: FakeConfigHeadRepository,
    fake_cache: FakeSnapshotCache,
    fake_outbox: FakeOutbox,
) -> ConfigurationUseCases:
    return ConfigurationUseCases(fake_repo, fake_cache, fake_outbox)


@pytest.fixture
def category_read_use_cases(
    fake_repo: FakeConfigHeadRepository, fake_cache: FakeSnapshotCache
) -> CategoryReadUseCases:
    return CategoryReadUseCases(fake_repo, fake_cache)


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


def minimal_content(entity_type: str, **overrides: Any) -> dict[str, Any]:
    """A minimal, gate-passing `definition_document` for `entity_type`, with `overrides` merged
    shallowly on top -- the one fixture point every gate/use-case/API test builds its scenario
    from, so a whitelist-seed change only needs updating here."""
    base: dict[str, Any]
    if entity_type == "category":
        base = {
            "descriptor": {"name": {"uz_latn": "Housing"}},
            "parent_category_id": None,
            "path": "/housing",
            "form_definition_id": str(overrides.pop("form_definition_id", UUID(int=0))),
            "tree_status": "ACTIVE",
        }
    elif entity_type == "form-definition":
        base = {
            "descriptor": {"name": {"uz_latn": "Housing form"}},
            "sections": [{"code": "main", "label": {"uz_latn": "Main"}, "order": 1}],
            "fields": [],
        }
    elif entity_type == "product-definition":
        base = {
            "descriptor": {"name": {"uz_latn": "Premium"}},
            "product_type": "SUBSCRIPTION",
            "price_amount": "10.00",
            "price_currency": "UZS",
        }
    elif entity_type == "placement-slot":
        base = {
            "descriptor": {"name": {"uz_latn": "Hero banner"}},
            "slot_key": "hero-1",
            "page_zone": "HOMEPAGE_HERO",
        }
    elif entity_type == "role-definition":
        base = {
            "descriptor": {"name": {"uz_latn": "Content Editor"}},
            "role_name": "Content Editor",
            "permission_keys": ["config:notification-template:manage"],
        }
    elif entity_type == "search-configuration":
        base = {
            "descriptor": {"name": {"uz_latn": "Default search"}},
            "sort_options": ["RELEVANCE", "RECENCY"],
            "default_sort": "RELEVANCE",
            "promotion_page_cap": 5,
        }
    elif entity_type == "notification-template":
        base = {
            "descriptor": {"name": {"uz_latn": "Listing published"}},
            "event_key": "ListingPublished",
            "channel": "EMAIL",
            "subject": {"uz_latn": "Your listing is live"},
            "body": {"uz_latn": "Congratulations"},
        }
    elif entity_type == "platform-settings":
        base = {
            "descriptor": {"name": {"uz_latn": "Global settings"}},
            "settings_scope": "GLOBAL",
            "settings": {},
        }
    else:
        raise ValueError(f"no minimal content fixture for entity type {entity_type!r}")
    base.update(overrides)
    return base


@pytest.fixture
def content_factory() -> Any:
    return minimal_content
