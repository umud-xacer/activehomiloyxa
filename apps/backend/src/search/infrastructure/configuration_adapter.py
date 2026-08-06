"""Reads the published `SearchConfiguration` snapshot from `configuration` -- never
`configuration.domain`/`application`/`infrastructure` (`cross-module-search`,
tools/importlinter.cfg; the ONE other module search may import at all, SAD Sec 8.1). Mirrors
`catalog.infrastructure.configuration_adapter`'s own narrow-Protocol bridge pattern.

`SearchConfiguration` (Config Framework Sec 3.8/3.9; `configuration.domain.content.
SearchConfigurationContent`) is scoped per category via `scope_category_id` (`None` = global).
No exact head `code` naming convention is documented for this entity type (unlike
`platform-settings-global`'s own literal seeded code) -- this adapter lists every published
`search-configuration` head and matches on `scope_category_id` found inside each one's own
published snapshot, preferring an exact category match and falling back to the global
(`scope_category_id is None`) head. Flagged in README "Known gaps" as an inferred, not literally
documented, lookup strategy.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from search.application.exceptions import NoSearchConfigurationPublishedError
from search.application.ports import SearchConfigurationSnapshot
from search.domain import SortOption
from shared_kernel import LocalizedText

_SORT_OPTION_VALUES = {option.value for option in SortOption}


class _ConfigurationReader(Protocol):
    """The narrow slice of `configuration.interfaces.ports.ConfigurationPort` this module
    actually calls."""

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> Any: ...

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> Any: ...


class ConfigurationSearchConfigurationAdapter:
    """Implements `search.application.ports.ConfigurationSnapshotPort`."""

    def __init__(self, configuration: _ConfigurationReader) -> None:
        self._configuration = configuration

    async def get_search_configuration(
        self, category_id: UUID | None
    ) -> SearchConfigurationSnapshot:
        global_snapshot: dict[str, Any] | None = None
        cursor: str | None = None
        while True:
            page = await self._configuration.list_config_heads(
                "search-configuration", cursor=cursor, limit=50
            )
            for head in page.items:
                if head.current_version_id is None:
                    continue
                version = await self._configuration.get_config_version(
                    "search-configuration", head.id, head.current_version_id
                )
                if version.status != "PUBLISHED" or version.snapshot is None:
                    continue
                snapshot = version.snapshot
                scope_category_id = snapshot.get("scope_category_id")
                if category_id is not None and scope_category_id == str(category_id):
                    return _to_snapshot(snapshot)
                if scope_category_id is None:
                    global_snapshot = snapshot
            cursor = page.page.next_cursor
            if cursor is None:
                break
        if global_snapshot is not None:
            return _to_snapshot(global_snapshot)
        raise NoSearchConfigurationPublishedError(category_id)


def _to_snapshot(raw: dict[str, Any]) -> SearchConfigurationSnapshot:
    raw_facets = raw.get("facets", [])
    facet_field_codes = tuple(f["field_code"] for f in raw_facets)
    # The authored label travels with the code. `configuration` stores it as a `LocalizedText`
    # document; anything else in that slot is ignored rather than guessed at, so the interface
    # falls back to the field code exactly as it did before labels existed here.
    facet_labels = tuple(
        (f["field_code"], LocalizedText(**f["label"]))
        for f in raw_facets
        if isinstance(f.get("label"), dict)
    )
    sort_options = tuple(
        SortOption(s) for s in raw.get("sort_options", []) if s in _SORT_OPTION_VALUES
    )
    default_sort_raw = raw.get("default_sort")
    default_sort = (
        SortOption(default_sort_raw)
        if default_sort_raw in _SORT_OPTION_VALUES
        else SortOption.RELEVANCE
    )
    return SearchConfigurationSnapshot(
        facet_field_codes=facet_field_codes,
        facet_labels=facet_labels,
        sort_options=sort_options,
        default_sort=default_sort,
        promotion_page_cap=int(raw["promotion_page_cap"]),
    )
