"""The three public `Categories`-tagged read use cases (`listCategories`, `getCategory`,
`getCategoryForm` -- `contracts/openapi.yaml`). Unauthenticated, snapshot-served (Config
Framework Sec 2.4: "served from a cached snapshot and refreshed on ConfigurationChanged"; DDD
Sec 8.3.3 "degrade gracefully on the last good snapshot"). Deliberately separate from
`ConfigurationUseCases`: these read the *resolved* consumer-facing snapshot, never a draft, and
carry none of the admin authoring/publish machinery.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from configuration.application.ports import ConfigHeadRepository, SnapshotCachePort
from configuration.domain import ConfigEntityType


class CategoryReadUseCases:
    def __init__(self, repo: ConfigHeadRepository, snapshot_cache: SnapshotCachePort) -> None:
        self._repo = repo
        self._cache = snapshot_cache

    async def list_categories(
        self, *, parent_id: UUID | None, include_retired: bool
    ) -> list[dict[str, Any]]:
        snapshots = await self._cache.list_current(ConfigEntityType.CATEGORY)
        results: list[dict[str, Any]] = []
        for snapshot in snapshots:
            if not include_retired and snapshot.get("tree_status") == "RETIRED":
                continue
            snapshot_parent = snapshot.get("parent_category_id")
            if parent_id is not None and snapshot_parent != str(parent_id):
                continue
            if parent_id is None and snapshot_parent is not None:
                continue
            results.append(snapshot)
        return results

    async def get_category(self, category_id: UUID) -> dict[str, Any] | None:
        head = await self._repo.get_head(ConfigEntityType.CATEGORY, category_id)
        if head is None:
            return None
        return await self._cache.get(ConfigEntityType.CATEGORY, head.code)

    async def get_category_form(self, category_id: UUID) -> dict[str, Any] | None:
        category_head = await self._repo.get_head(ConfigEntityType.CATEGORY, category_id)
        if category_head is None:
            return None
        category_snapshot = await self._cache.get(ConfigEntityType.CATEGORY, category_head.code)
        if category_snapshot is None:
            return None
        form_id = category_snapshot.get("form_definition_id")
        if not form_id:
            return None
        form_head = await self._repo.get_head(ConfigEntityType.FORM_DEFINITION, UUID(str(form_id)))
        if form_head is None:
            return None
        return await self._cache.get(ConfigEntityType.FORM_DEFINITION, form_head.code)
