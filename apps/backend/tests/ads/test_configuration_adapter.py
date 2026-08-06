"""Unit tests for `ConfigurationPlacementSlotAdapter` against a fake `_ConfigurationReader`."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from ads.infrastructure.configuration_adapter import ConfigurationPlacementSlotAdapter


@dataclass
class _FakeConfigurationReader:
    heads: list[object] = field(default_factory=list)
    versions: dict[UUID, object] = field(default_factory=dict)

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> object:
        assert entity_type == "placement-slot"
        return SimpleNamespace(items=self.heads, page=SimpleNamespace(next_cursor=None))

    async def get_config_version(self, entity_type: str, head_id: UUID, version_id: UUID) -> object:
        assert entity_type == "placement-slot"
        return self.versions[version_id]

    def seed(self, *, slot_key: str, published: bool = True) -> UUID:
        head_id = uuid4()
        version_id = uuid4()
        self.heads.append(
            SimpleNamespace(id=head_id, code=f"code-{slot_key}", current_version_id=version_id)
        )
        self.versions[version_id] = SimpleNamespace(
            id=version_id,
            status="PUBLISHED" if published else "DRAFT",
            snapshot={"slot_key": slot_key} if published else None,
        )
        return head_id


@pytest.mark.asyncio
async def test_get_slot_by_key_finds_a_published_slot_by_its_content_slot_key() -> None:
    reader = _FakeConfigurationReader()
    head_id = reader.seed(slot_key="HOMEPAGE_TOP")
    adapter = ConfigurationPlacementSlotAdapter(reader)
    snapshot = await adapter.get_slot_by_key("HOMEPAGE_TOP")
    assert snapshot is not None
    assert snapshot.head_id == head_id
    assert snapshot.slot_key == "HOMEPAGE_TOP"


@pytest.mark.asyncio
async def test_get_slot_by_key_returns_none_for_an_unknown_key() -> None:
    reader = _FakeConfigurationReader()
    reader.seed(slot_key="HOMEPAGE_TOP")
    adapter = ConfigurationPlacementSlotAdapter(reader)
    assert await adapter.get_slot_by_key("NO_SUCH_SLOT") is None


@pytest.mark.asyncio
async def test_get_slot_by_key_ignores_a_draft_version() -> None:
    reader = _FakeConfigurationReader()
    reader.seed(slot_key="HOMEPAGE_TOP", published=False)
    adapter = ConfigurationPlacementSlotAdapter(reader)
    assert await adapter.get_slot_by_key("HOMEPAGE_TOP") is None
