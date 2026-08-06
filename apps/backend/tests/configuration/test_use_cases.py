"""`ConfigurationUseCases` -- the generic authoring/publish/query orchestration, exercised
against the in-memory fakes in `conftest.py` (real-Postgres coverage of the same flows lives in
`integration/`)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from apps.backend.tests.configuration.conftest import (
    FakeOutbox,
    FakeSnapshotCache,
    minimal_content,
)

from configuration.application.exceptions import (
    ConfigHeadNotFoundError,
    ConfigVersionNotFoundError,
    GateFailedError,
    VersionNotPublishableError,
)
from configuration.application.use_cases import ConfigurationUseCases
from configuration.domain import (
    ApproverPermissionError,
    ConfigHead,
    ConfigVersion,
    SelfApprovalError,
)
from configuration.domain.entity_types import ConfigEntityType
from configuration.domain.lifecycle import VersionStatus

MAKER = uuid4()
CHECKER = uuid4()


async def _publish_standalone_search_config(
    use_cases: ConfigurationUseCases, now: datetime
) -> tuple[ConfigHead, ConfigVersion]:
    """STANDARD-track (search-configuration): one call publishes directly."""
    head, version = await use_cases.create_draft(
        ConfigEntityType.SEARCH_CONFIGURATION,
        code="search-default",
        business_owner="Product Owner",
        definition=minimal_content("search-configuration"),
        actor_id=MAKER,
        now=now,
    )
    published = await use_cases.publish(
        ConfigEntityType.SEARCH_CONFIGURATION,
        head.id,
        version.id,
        actor_id=MAKER,
        actor_permission_keys=frozenset({"config:search-configuration:manage"}),
        approval_note=None,
        now=now,
    )
    return head, published


@pytest.mark.asyncio
async def test_create_draft_then_duplicate_code_refused(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    await use_cases.create_draft(
        ConfigEntityType.SEARCH_CONFIGURATION,
        code="search-default",
        business_owner="Product Owner",
        definition=minimal_content("search-configuration"),
        actor_id=MAKER,
        now=now,
    )
    with pytest.raises(Exception) as exc_info:
        await use_cases.create_draft(
            ConfigEntityType.SEARCH_CONFIGURATION,
            code="search-default",
            business_owner="Product Owner",
            definition=minimal_content("search-configuration"),
            actor_id=MAKER,
            now=now,
        )
    assert type(exc_info.value).__name__ == "DuplicateCodeError"


@pytest.mark.asyncio
async def test_create_version_draft_on_unknown_head_raises_not_found(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    with pytest.raises(ConfigHeadNotFoundError):
        await use_cases.create_version_draft(
            ConfigEntityType.SEARCH_CONFIGURATION,
            uuid4(),
            definition=minimal_content("search-configuration"),
            actor_id=MAKER,
            now=now,
        )


@pytest.mark.asyncio
async def test_get_version_on_unknown_version_raises_not_found(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    head, _version = await use_cases.create_draft(
        ConfigEntityType.SEARCH_CONFIGURATION,
        code="search-default",
        business_owner="Product Owner",
        definition=minimal_content("search-configuration"),
        actor_id=MAKER,
        now=now,
    )
    with pytest.raises(ConfigVersionNotFoundError):
        await use_cases.get_version(ConfigEntityType.SEARCH_CONFIGURATION, head.id, uuid4())


@pytest.mark.asyncio
async def test_validate_reports_gate_errors_without_mutating_status(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    head, version = await use_cases.create_draft(
        ConfigEntityType.SEARCH_CONFIGURATION,
        code="search-default",
        business_owner="Product Owner",
        definition=minimal_content("search-configuration", default_sort="NOT_ENABLED"),
        actor_id=MAKER,
        now=now,
    )
    result = await use_cases.validate(ConfigEntityType.SEARCH_CONFIGURATION, head.id, version.id)
    assert not result.valid
    reloaded = await use_cases.get_version(
        ConfigEntityType.SEARCH_CONFIGURATION, head.id, version.id
    )
    assert reloaded.status is VersionStatus.DRAFT  # validate() is a dry run, never mutates


@pytest.mark.asyncio
async def test_standard_track_publish_is_a_single_call(
    use_cases: ConfigurationUseCases,
    fake_cache: FakeSnapshotCache,
    fake_outbox: FakeOutbox,
    now: datetime,
) -> None:
    _head, published = await _publish_standalone_search_config(use_cases, now)
    assert published.status is VersionStatus.PUBLISHED
    assert published.published_by == MAKER
    assert published.approved_by is None
    cached = await fake_cache.get(ConfigEntityType.SEARCH_CONFIGURATION, "search-default")
    assert cached is not None
    assert len(fake_outbox.events) == 1
    assert fake_outbox.events[0].event_type == "SearchConfigurationChanged"


@pytest.mark.asyncio
async def test_publish_on_already_published_version_refused(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    head, published = await _publish_standalone_search_config(use_cases, now)
    with pytest.raises(VersionNotPublishableError):
        await use_cases.publish(
            ConfigEntityType.SEARCH_CONFIGURATION,
            head.id,
            published.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({"config:search-configuration:manage"}),
            approval_note=None,
            now=now,
        )


@pytest.mark.asyncio
async def test_gate_failure_on_publish_returns_version_to_draft(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    head, version = await use_cases.create_draft(
        ConfigEntityType.SEARCH_CONFIGURATION,
        code="search-default",
        business_owner="Product Owner",
        definition=minimal_content("search-configuration", promotion_page_cap=-1),
        actor_id=MAKER,
        now=now,
    )
    with pytest.raises(GateFailedError):
        await use_cases.publish(
            ConfigEntityType.SEARCH_CONFIGURATION,
            head.id,
            version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({"config:search-configuration:manage"}),
            approval_note=None,
            now=now,
        )
    reloaded = await use_cases.get_version(
        ConfigEntityType.SEARCH_CONFIGURATION, head.id, version.id
    )
    assert reloaded.status is VersionStatus.DRAFT


@pytest.mark.asyncio
async def test_controlled_track_requires_two_calls(
    use_cases: ConfigurationUseCases, fake_outbox: FakeOutbox, now: datetime
) -> None:
    head, version = await use_cases.create_draft(
        ConfigEntityType.ROLE_DEFINITION,
        code="content-editor",
        business_owner="Super Administrator",
        definition=minimal_content("role-definition"),
        actor_id=MAKER,
        now=now,
    )
    after_maker = await use_cases.publish(
        ConfigEntityType.ROLE_DEFINITION,
        head.id,
        version.id,
        actor_id=MAKER,
        actor_permission_keys=frozenset({"config:role-definition:manage"}),
        approval_note="please review",
        now=now,
    )
    assert after_maker.status is VersionStatus.APPROVAL
    assert fake_outbox.events == []  # not published yet -- no event on submission

    published = await use_cases.publish(
        ConfigEntityType.ROLE_DEFINITION,
        head.id,
        version.id,
        actor_id=CHECKER,
        actor_permission_keys=frozenset(
            {"config:role-definition:manage", "config:role-definition:approve"}
        ),
        approval_note="approved",
        now=now,
    )
    assert published.status is VersionStatus.PUBLISHED
    assert published.approved_by == CHECKER
    assert len(fake_outbox.events) == 1


@pytest.mark.asyncio
async def test_I16_self_approval_on_controlled_track_refused(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    head, version = await use_cases.create_draft(
        ConfigEntityType.ROLE_DEFINITION,
        code="content-editor",
        business_owner="Super Administrator",
        definition=minimal_content("role-definition"),
        actor_id=MAKER,
        now=now,
    )
    await use_cases.publish(
        ConfigEntityType.ROLE_DEFINITION,
        head.id,
        version.id,
        actor_id=MAKER,
        actor_permission_keys=frozenset({"config:role-definition:manage"}),
        approval_note=None,
        now=now,
    )
    with pytest.raises(SelfApprovalError):
        await use_cases.publish(
            ConfigEntityType.ROLE_DEFINITION,
            head.id,
            version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset(
                {"config:role-definition:manage", "config:role-definition:approve"}
            ),
            approval_note=None,
            now=now,
        )


@pytest.mark.asyncio
async def test_checker_without_approve_permission_refused(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    head, version = await use_cases.create_draft(
        ConfigEntityType.ROLE_DEFINITION,
        code="content-editor",
        business_owner="Super Administrator",
        definition=minimal_content("role-definition"),
        actor_id=MAKER,
        now=now,
    )
    await use_cases.publish(
        ConfigEntityType.ROLE_DEFINITION,
        head.id,
        version.id,
        actor_id=MAKER,
        actor_permission_keys=frozenset({"config:role-definition:manage"}),
        approval_note=None,
        now=now,
    )
    with pytest.raises(ApproverPermissionError):
        await use_cases.publish(
            ConfigEntityType.ROLE_DEFINITION,
            head.id,
            version.id,
            actor_id=CHECKER,
            actor_permission_keys=frozenset({"config:role-definition:manage"}),
            approval_note=None,
            now=now,
        )


@pytest.mark.asyncio
async def test_second_publish_deprecates_previous_current_version(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    head, v1 = await _publish_standalone_search_config(use_cases, now)
    v2_draft = await use_cases.create_version_draft(
        ConfigEntityType.SEARCH_CONFIGURATION,
        head.id,
        definition=minimal_content("search-configuration", promotion_page_cap=10),
        actor_id=MAKER,
        now=now,
    )
    await use_cases.publish(
        ConfigEntityType.SEARCH_CONFIGURATION,
        head.id,
        v2_draft.id,
        actor_id=MAKER,
        actor_permission_keys=frozenset({"config:search-configuration:manage"}),
        approval_note=None,
        now=now,
    )
    reloaded_v1 = await use_cases.get_version(ConfigEntityType.SEARCH_CONFIGURATION, head.id, v1.id)
    assert reloaded_v1.status is VersionStatus.DEPRECATED
    reloaded_head = await use_cases.get_head(ConfigEntityType.SEARCH_CONFIGURATION, head.id)
    assert reloaded_head.current_version_id == v2_draft.id


@pytest.mark.asyncio
async def test_rollback_creates_new_draft_pointing_at_target_and_republishes(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    head, v1 = await _publish_standalone_search_config(use_cases, now)
    v2_draft = await use_cases.create_version_draft(
        ConfigEntityType.SEARCH_CONFIGURATION,
        head.id,
        definition=minimal_content("search-configuration", promotion_page_cap=10),
        actor_id=MAKER,
        now=now,
    )
    await use_cases.publish(
        ConfigEntityType.SEARCH_CONFIGURATION,
        head.id,
        v2_draft.id,
        actor_id=MAKER,
        actor_permission_keys=frozenset({"config:search-configuration:manage"}),
        approval_note=None,
        now=now,
    )

    rolled_back = await use_cases.rollback(
        ConfigEntityType.SEARCH_CONFIGURATION,
        head.id,
        target_version_id=v1.id,
        actor_id=MAKER,
        actor_permission_keys=frozenset({"config:search-configuration:manage"}),
        expedited=False,
        now=now,
    )
    assert rolled_back.status is VersionStatus.PUBLISHED
    assert rolled_back.rollback_of_version_id == v1.id
    assert rolled_back.definition_document == v1.definition_document
    assert rolled_back.version_number == 3

    reloaded_head = await use_cases.get_head(ConfigEntityType.SEARCH_CONFIGURATION, head.id)
    assert reloaded_head.current_version_id == rolled_back.id


@pytest.mark.asyncio
async def test_list_and_compare_versions(use_cases: ConfigurationUseCases, now: datetime) -> None:
    head, v1 = await _publish_standalone_search_config(use_cases, now)
    v2 = await use_cases.create_version_draft(
        ConfigEntityType.SEARCH_CONFIGURATION,
        head.id,
        definition=minimal_content("search-configuration", promotion_page_cap=99),
        actor_id=MAKER,
        now=now,
    )
    versions = await use_cases.list_versions(ConfigEntityType.SEARCH_CONFIGURATION, head.id)
    assert [v.version_number for v in versions] == [1, 2]

    diff = await use_cases.compare_versions(
        ConfigEntityType.SEARCH_CONFIGURATION, head.id, v1.id, v2.id
    )
    assert diff["changed"]["promotion_page_cap"] == {"from": 5, "to": 99}


@pytest.mark.asyncio
async def test_export_and_import_config(use_cases: ConfigurationUseCases, now: datetime) -> None:
    head, _published = await _publish_standalone_search_config(use_cases, now)
    exported = await use_cases.export_config(ConfigEntityType.SEARCH_CONFIGURATION, head.id, None)
    assert exported["code"] == "search-default"

    reimported = await use_cases.import_config(
        ConfigEntityType.SEARCH_CONFIGURATION,
        definition=exported,
        actor_id=MAKER,
        now=now,
    )
    assert reimported.status is VersionStatus.DRAFT
    assert reimported.head_id == head.id  # existing code -> new draft on the same head
    assert reimported.version_number == 2


@pytest.mark.asyncio
async def test_import_config_with_new_code_creates_new_head(
    use_cases: ConfigurationUseCases, now: datetime
) -> None:
    version = await use_cases.import_config(
        ConfigEntityType.SEARCH_CONFIGURATION,
        definition={
            "code": "search-mobile",
            "businessOwner": "Product Owner",
            "definition": minimal_content("search-configuration"),
        },
        actor_id=MAKER,
        now=now,
    )
    assert version.version_number == 1
    head = await use_cases.get_head(ConfigEntityType.SEARCH_CONFIGURATION, version.head_id)
    assert head.code == "search-mobile"
