"""Reads published `PlacementSlotDefinition` snapshots from `configuration` -- never
`configuration.domain`/`application`/`infrastructure` (`cross-module-ads`, tools/importlinter.cfg;
the only other module ads may import at all besides `media`, SAD Sec 8.1). Mirrors `billing.
infrastructure.configuration_adapter.ConfigurationProductDefinitionAdapter`'s own narrow-Protocol
bridge pattern exactly -- a `PlacementSlotDefinition` version's own content model
(`configuration.domain.content.PlacementSlotContent`) carries its `SlotKey` inside the version
content itself (`slot_key`), not as the head's own `code`, so this adapter lists every published
`placement-slot` head and matches on that field.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from ads.application.ports import SlotSnapshot


class _ConfigurationReader(Protocol):
    """The narrow slice of `configuration.interfaces.ports.ConfigurationPort` this module
    actually calls."""

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> Any: ...

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> Any: ...


class ConfigurationPlacementSlotAdapter:
    """Implements `ads.application.ports.PlacementSlotReaderPort`."""

    def __init__(self, configuration: _ConfigurationReader) -> None:
        self._configuration = configuration

    async def get_slot_by_key(self, slot_key: str) -> SlotSnapshot | None:
        cursor: str | None = None
        while True:
            page = await self._configuration.list_config_heads(
                "placement-slot", cursor=cursor, limit=50
            )
            for head in page.items:
                if head.current_version_id is None:
                    continue
                version = await self._configuration.get_config_version(
                    "placement-slot", head.id, head.current_version_id
                )
                if version.status != "PUBLISHED" or version.snapshot is None:
                    continue
                if version.snapshot.get("slot_key") == slot_key:
                    return SlotSnapshot(head_id=head.id, version_id=version.id, slot_key=slot_key)
            cursor = page.page.next_cursor
            if cursor is None:
                return None
