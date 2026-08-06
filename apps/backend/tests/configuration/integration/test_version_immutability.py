"""I-07: "An AttributeSet is always valid against the FormDefinition version bound to the
listing; config changes never retro-invalidate." Proven at BC-04's own boundary: a published
version's exact content remains retrievable, unchanged, by its own id forever, even after a
newer version supersedes it as the head's `current_version_id`."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from apps.backend.tests.configuration.conftest import minimal_content
from apps.backend.tests.configuration.integration.conftest import OpenUseCases

from configuration.domain.entity_types import ConfigEntityType
from configuration.domain.lifecycle import VersionStatus

MAKER = uuid4()


@pytest.mark.asyncio
async def test_I07_published_version_remains_retrievable_unchanged_after_superseded(
    open_use_cases: OpenUseCases,
) -> None:
    now = datetime.now(UTC)
    async with open_use_cases() as use_cases:
        head, v1 = await use_cases.create_draft(
            ConfigEntityType.SEARCH_CONFIGURATION,
            code="search-default",
            business_owner="Product Owner",
            definition=minimal_content("search-configuration", promotion_page_cap=5),
            actor_id=MAKER,
            now=now,
        )
    async with open_use_cases() as use_cases:
        published_v1 = await use_cases.publish(
            ConfigEntityType.SEARCH_CONFIGURATION,
            head.id,
            v1.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({"config:search-configuration:manage"}),
            approval_note=None,
            now=now,
        )
    original_definition = dict(published_v1.definition_document)

    async with open_use_cases() as use_cases:
        v2 = await use_cases.create_version_draft(
            ConfigEntityType.SEARCH_CONFIGURATION,
            head.id,
            definition=minimal_content("search-configuration", promotion_page_cap=99),
            actor_id=MAKER,
            now=now,
        )
    async with open_use_cases() as use_cases:
        await use_cases.publish(
            ConfigEntityType.SEARCH_CONFIGURATION,
            head.id,
            v2.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({"config:search-configuration:manage"}),
            approval_note=None,
            now=now,
        )

    async with open_use_cases() as use_cases:
        reloaded_v1 = await use_cases.get_version(
            ConfigEntityType.SEARCH_CONFIGURATION, head.id, v1.id
        )
        reloaded_head = await use_cases.get_head(ConfigEntityType.SEARCH_CONFIGURATION, head.id)

    assert reloaded_v1.definition_document == original_definition
    assert reloaded_v1.status is VersionStatus.DEPRECATED  # lifecycle moves on
    assert reloaded_head.current_version_id == v2.id  # head now points at v2
    assert reloaded_v1.definition_document["promotion_page_cap"] == 5  # v1's own content intact
