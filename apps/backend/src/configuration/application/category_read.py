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


def _category_sort_key(snapshot: dict[str, Any]) -> tuple[int, str]:
    """`RedisSnapshotCache.list_current` reads its index off a Redis SET (`SMEMBERS`), which has
    no guaranteed iteration order -- without an explicit sort here, `list_categories` returned
    whatever order the set happened to hand back, different on every call (the reported "homepage
    category chips shuffle on every refresh" bug). `display_order` ASC, `id` ASC as the tiebreak
    -- both already present on every snapshot (`descriptor.display_order`/`id`), matching how
    `SqlalchemyConfigHeadRepository.list_heads` orders its own (admin-only) Postgres query."""
    descriptor = snapshot.get("descriptor") or {}
    display_order = descriptor.get("display_order")
    return (display_order if isinstance(display_order, int) else 0, str(snapshot.get("id", "")))


class CategoryReadUseCases:
    def __init__(self, repo: ConfigHeadRepository, snapshot_cache: SnapshotCachePort) -> None:
        self._repo = repo
        self._cache = snapshot_cache

    async def list_categories(
        self, *, parent_id: UUID | None, include_retired: bool, include_descendants: bool = False
    ) -> list[dict[str, Any]]:
        """`include_descendants` (additive, backward-compatible -- default False leaves every
        existing caller's behaviour unchanged) skips the parent-level filter entirely and returns
        every category at every depth in the one cache read this method already does regardless
        (`self._cache.list_current` has no per-level cost). Added because `catalog-client.ts`'s
        `fetchAllCategoriesRecursive` had to reconstruct the whole taxonomy with one HTTP round
        trip per tree node (bounded-concurrency BFS, one level at a time) since that was the only
        way to get a flat list through this endpoint -- fine at the taxonomy's original size, a
        genuine multi-second stall once the taxonomy grew to 100+ categories (confirmed live)."""
        snapshots = await self._cache.list_current(ConfigEntityType.CATEGORY)
        results: list[dict[str, Any]] = []
        for snapshot in snapshots:
            if not include_retired and snapshot.get("tree_status") == "RETIRED":
                continue
            if not include_descendants:
                snapshot_parent = snapshot.get("parent_category_id")
                if parent_id is not None and snapshot_parent != str(parent_id):
                    continue
                if parent_id is None and snapshot_parent is not None:
                    continue
            results.append(snapshot)
        results.sort(key=_category_sort_key)
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
