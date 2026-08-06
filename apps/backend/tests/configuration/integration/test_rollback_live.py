"""Rollback (Config Framework Sec 2.6): re-publishing a prior version's content as a new draft,
re-running the gate ("the same re-validate-on-re-entry discipline"), against real Postgres."""

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
async def test_rollback_republishes_target_content_as_a_new_version(
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
        await use_cases.publish(
            ConfigEntityType.SEARCH_CONFIGURATION,
            head.id,
            v1.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({"config:search-configuration:manage"}),
            approval_note=None,
            now=now,
        )

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
        rolled_back = await use_cases.rollback(
            ConfigEntityType.SEARCH_CONFIGURATION,
            head.id,
            target_version_id=v1.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({"config:search-configuration:manage"}),
            expedited=True,
            now=now,
        )

    assert rolled_back.status is VersionStatus.PUBLISHED
    assert rolled_back.rollback_of_version_id == v1.id
    assert rolled_back.definition_document["promotion_page_cap"] == 5
    assert rolled_back.version_number == 3

    async with open_use_cases() as use_cases:
        reloaded_head = await use_cases.get_head(ConfigEntityType.SEARCH_CONFIGURATION, head.id)
    assert reloaded_head.current_version_id == rolled_back.id
