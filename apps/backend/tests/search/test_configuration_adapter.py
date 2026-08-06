"""Unit tests for `ConfigurationSearchConfigurationAdapter` against a fake of the narrow
`_ConfigurationReader` slice it actually calls -- no real Postgres needed. Mirrors
`apps/backend/tests/catalog/test_configuration_adapter.py`'s pattern."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from configuration.interfaces.dto import (
    ConfigurationHead,
    ConfigurationHeadPage,
    ConfigurationVersion,
    PageInfo,
)
from search.application.exceptions import NoSearchConfigurationPublishedError
from search.domain import SortOption
from search.infrastructure.configuration_adapter import ConfigurationSearchConfigurationAdapter


@dataclass
class FakeConfigurationReader:
    """Implements `search.infrastructure.configuration_adapter._ConfigurationReader`."""

    heads: list[ConfigurationHead] = field(default_factory=list)
    versions: dict[UUID, ConfigurationVersion] = field(default_factory=dict)

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> ConfigurationHeadPage:
        matching = [h for h in self.heads if h.entity_type == entity_type]
        return ConfigurationHeadPage(
            items=matching, page=PageInfo(limit=limit or 20, next_cursor=None)
        )

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> ConfigurationVersion:
        return self.versions[version_id]


def _head(*, version_id: UUID | None) -> ConfigurationHead:
    return ConfigurationHead(
        id=uuid4(),
        entity_type="search-configuration",
        code=f"search-config-{uuid4()}",
        current_version_id=version_id,
        status="PUBLISHED",
    )


def _version(
    *, version_id: UUID, status: str = "PUBLISHED", snapshot: dict[str, Any] | None
) -> ConfigurationVersion:
    return ConfigurationVersion(
        id=version_id,
        head_id=uuid4(),
        version_number=1,
        status=status,  # type: ignore[arg-type]
        definition={},
        snapshot=snapshot,
    )


def _snapshot(
    *,
    scope_category_id: UUID | None = None,
    facets: list[str] | None = None,
    sort_options: list[str] | None = None,
    default_sort: str = "RELEVANCE",
    promotion_page_cap: int = 3,
) -> dict[str, Any]:
    return {
        "scope_category_id": str(scope_category_id) if scope_category_id else None,
        "facets": [{"field_code": code} for code in (facets or [])],
        "sort_options": sort_options or ["RELEVANCE"],
        "default_sort": default_sort,
        "promotion_page_cap": promotion_page_cap,
    }


class TestGetSearchConfiguration:
    async def test_I01_returns_the_global_snapshot_when_no_category_scoped_one_exists(
        self,
    ) -> None:
        version_id = uuid4()
        reader = FakeConfigurationReader(
            heads=[_head(version_id=version_id)],
            versions={
                version_id: _version(
                    version_id=version_id,
                    snapshot=_snapshot(facets=["condition"], promotion_page_cap=2),
                )
            },
        )
        adapter = ConfigurationSearchConfigurationAdapter(reader)
        snapshot = await adapter.get_search_configuration(uuid4())
        assert snapshot.facet_field_codes == ("condition",)
        assert snapshot.promotion_page_cap == 2

    async def test_I02_prefers_an_exact_category_scoped_snapshot_over_the_global_one(self) -> None:
        category_id = uuid4()
        global_version_id, scoped_version_id = uuid4(), uuid4()
        reader = FakeConfigurationReader(
            heads=[_head(version_id=global_version_id), _head(version_id=scoped_version_id)],
            versions={
                global_version_id: _version(
                    version_id=global_version_id,
                    snapshot=_snapshot(facets=["condition"], promotion_page_cap=1),
                ),
                scoped_version_id: _version(
                    version_id=scoped_version_id,
                    snapshot=_snapshot(
                        scope_category_id=category_id, facets=["rooms"], promotion_page_cap=5
                    ),
                ),
            },
        )
        adapter = ConfigurationSearchConfigurationAdapter(reader)
        snapshot = await adapter.get_search_configuration(category_id)
        assert snapshot.facet_field_codes == ("rooms",)
        assert snapshot.promotion_page_cap == 5

    async def test_I03_raises_when_no_configuration_has_ever_been_published(self) -> None:
        reader = FakeConfigurationReader(heads=[])
        adapter = ConfigurationSearchConfigurationAdapter(reader)
        with pytest.raises(NoSearchConfigurationPublishedError):
            await adapter.get_search_configuration(uuid4())

    async def test_I04_skips_a_head_with_no_current_version(self) -> None:
        reader = FakeConfigurationReader(heads=[_head(version_id=None)])
        adapter = ConfigurationSearchConfigurationAdapter(reader)
        with pytest.raises(NoSearchConfigurationPublishedError):
            await adapter.get_search_configuration(None)

    async def test_I05_skips_a_non_published_version(self) -> None:
        version_id = uuid4()
        reader = FakeConfigurationReader(
            heads=[_head(version_id=version_id)],
            versions={
                version_id: _version(version_id=version_id, status="DRAFT", snapshot=_snapshot())
            },
        )
        adapter = ConfigurationSearchConfigurationAdapter(reader)
        with pytest.raises(NoSearchConfigurationPublishedError):
            await adapter.get_search_configuration(None)

    async def test_I06_ignores_an_unrecognized_sort_option_value(self) -> None:
        version_id = uuid4()
        reader = FakeConfigurationReader(
            heads=[_head(version_id=version_id)],
            versions={
                version_id: _version(
                    version_id=version_id,
                    snapshot=_snapshot(sort_options=["RELEVANCE", "NOT_A_REAL_SORT"]),
                )
            },
        )
        adapter = ConfigurationSearchConfigurationAdapter(reader)
        snapshot = await adapter.get_search_configuration(None)
        assert snapshot.sort_options == (SortOption.RELEVANCE,)

    async def test_I07_defaults_default_sort_to_relevance_when_unrecognized_or_absent(
        self,
    ) -> None:
        version_id = uuid4()
        reader = FakeConfigurationReader(
            heads=[_head(version_id=version_id)],
            versions={
                version_id: _version(
                    version_id=version_id, snapshot=_snapshot(default_sort="NOT_A_REAL_SORT")
                )
            },
        )
        adapter = ConfigurationSearchConfigurationAdapter(reader)
        snapshot = await adapter.get_search_configuration(None)
        assert snapshot.default_sort == SortOption.RELEVANCE
