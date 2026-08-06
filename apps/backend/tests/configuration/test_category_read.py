"""`CategoryReadUseCases` -- the three public unauthenticated `Categories` reads, served from
the resolved snapshot cache, never a draft (Config Framework Sec 2.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from apps.backend.tests.configuration.conftest import (
    FakeConfigHeadRepository,
    FakeSnapshotCache,
    minimal_content,
)

from configuration.application.category_read import CategoryReadUseCases
from configuration.application.use_cases import ConfigurationUseCases
from configuration.domain import ConfigHead, HeadStatus
from configuration.domain.entity_types import ConfigEntityType

MAKER = uuid4()


async def _publish_form_and_category(
    use_cases: ConfigurationUseCases, now: datetime, *, tree_status: str = "ACTIVE"
) -> tuple[ConfigHead, ConfigHead]:
    form_head, form_version = await use_cases.create_draft(
        ConfigEntityType.FORM_DEFINITION,
        code="housing-form",
        business_owner="Product Owner",
        definition=minimal_content("form-definition"),
        actor_id=MAKER,
        now=now,
    )
    await use_cases.publish(
        ConfigEntityType.FORM_DEFINITION,
        form_head.id,
        form_version.id,
        actor_id=MAKER,
        actor_permission_keys=frozenset({"config:form-definition:manage"}),
        approval_note="submit",
        now=now,
    )
    await use_cases.publish(
        ConfigEntityType.FORM_DEFINITION,
        form_head.id,
        form_version.id,
        actor_id=uuid4(),
        actor_permission_keys=frozenset(
            {"config:form-definition:manage", "config:form-definition:approve"}
        ),
        approval_note="approve",
        now=now,
    )

    cat_head, cat_version = await use_cases.create_draft(
        ConfigEntityType.CATEGORY,
        code="housing",
        business_owner="Product Owner",
        definition=minimal_content(
            "category", form_definition_id=form_head.id, tree_status=tree_status
        ),
        actor_id=MAKER,
        now=now,
    )
    await use_cases.publish(
        ConfigEntityType.CATEGORY,
        cat_head.id,
        cat_version.id,
        actor_id=MAKER,
        actor_permission_keys=frozenset({"config:category:manage"}),
        approval_note="submit",
        now=now,
    )
    await use_cases.publish(
        ConfigEntityType.CATEGORY,
        cat_head.id,
        cat_version.id,
        actor_id=uuid4(),
        actor_permission_keys=frozenset({"config:category:manage", "config:category:approve"}),
        approval_note="approve",
        now=now,
    )
    return form_head, cat_head


@pytest.mark.asyncio
async def test_get_category_returns_published_snapshot(
    use_cases: ConfigurationUseCases,
    category_read_use_cases: CategoryReadUseCases,
    now: datetime,
) -> None:
    _form_head, cat_head = await _publish_form_and_category(use_cases, now)
    snapshot = await category_read_use_cases.get_category(cat_head.id)
    assert snapshot is not None
    assert snapshot["code"] == "housing"


@pytest.mark.asyncio
async def test_get_category_unknown_id_returns_none(
    category_read_use_cases: CategoryReadUseCases,
) -> None:
    assert await category_read_use_cases.get_category(uuid4()) is None


@pytest.mark.asyncio
async def test_get_category_form_resolves_the_one_directional_binding(
    use_cases: ConfigurationUseCases,
    category_read_use_cases: CategoryReadUseCases,
    now: datetime,
) -> None:
    """Regression coverage (this session's fixed bug): the category snapshot carries
    `form_definition_id`; the form itself carries no back-reference. `get_category_form` must
    resolve the binding via the category, not expect the form to know its category."""
    form_head, cat_head = await _publish_form_and_category(use_cases, now)
    snapshot = await category_read_use_cases.get_category_form(cat_head.id)
    assert snapshot is not None
    assert snapshot["id"] == str(form_head.id)
    assert "category_id" not in snapshot


@pytest.mark.asyncio
async def test_get_category_form_unknown_category_returns_none(
    category_read_use_cases: CategoryReadUseCases,
) -> None:
    assert await category_read_use_cases.get_category_form(uuid4()) is None


@pytest.mark.asyncio
async def test_list_categories_excludes_retired_by_default(
    use_cases: ConfigurationUseCases,
    category_read_use_cases: CategoryReadUseCases,
    now: datetime,
) -> None:
    await _publish_form_and_category(use_cases, now, tree_status="RETIRED")
    active_only = await category_read_use_cases.list_categories(
        parent_id=None, include_retired=False
    )
    assert active_only == []

    with_retired = await category_read_use_cases.list_categories(
        parent_id=None, include_retired=True
    )
    assert len(with_retired) == 1


@pytest.mark.asyncio
async def test_list_categories_filters_by_parent(
    use_cases: ConfigurationUseCases,
    category_read_use_cases: CategoryReadUseCases,
    now: datetime,
) -> None:
    _form_head, _cat_head = await _publish_form_and_category(use_cases, now)
    top_level = await category_read_use_cases.list_categories(parent_id=None, include_retired=False)
    assert len(top_level) == 1

    under_other_parent = await category_read_use_cases.list_categories(
        parent_id=uuid4(), include_retired=False
    )
    assert under_other_parent == []


def _bare_head(
    entity_type: ConfigEntityType, code: str, *, current_version_id: object = None
) -> ConfigHead:
    now = datetime.now(UTC)
    return ConfigHead(
        id=uuid4(),
        entity_type=entity_type,
        code=code,
        current_version_id=current_version_id,  # type: ignore[arg-type]
        status=HeadStatus.PUBLISHED,
        business_owner="Product Owner",
        created_at=now,
        created_by=MAKER,
        updated_at=now,
        updated_by=MAKER,
    )


@pytest.mark.asyncio
async def test_list_categories_excludes_child_categories_when_listing_top_level(
    fake_repo: FakeConfigHeadRepository,
    fake_cache: FakeSnapshotCache,
    category_read_use_cases: CategoryReadUseCases,
) -> None:
    """A child category (has `parent_category_id`) must not appear in a `parent_id=None`
    (top-level) listing."""
    await fake_cache.put(
        ConfigEntityType.CATEGORY,
        "sub-housing",
        {"code": "sub-housing", "parent_category_id": str(uuid4())},
    )
    top_level = await category_read_use_cases.list_categories(parent_id=None, include_retired=False)
    assert top_level == []


@pytest.mark.asyncio
async def test_get_category_form_returns_none_when_category_snapshot_not_yet_cached(
    fake_repo: FakeConfigHeadRepository,
    category_read_use_cases: CategoryReadUseCases,
) -> None:
    head = _bare_head(ConfigEntityType.CATEGORY, "housing", current_version_id=uuid4())
    fake_repo.heads[(ConfigEntityType.CATEGORY, head.id)] = head
    assert await category_read_use_cases.get_category_form(head.id) is None


@pytest.mark.asyncio
async def test_get_category_form_returns_none_when_category_has_no_bound_form(
    fake_repo: FakeConfigHeadRepository,
    fake_cache: FakeSnapshotCache,
    category_read_use_cases: CategoryReadUseCases,
) -> None:
    head = _bare_head(ConfigEntityType.CATEGORY, "housing", current_version_id=uuid4())
    fake_repo.heads[(ConfigEntityType.CATEGORY, head.id)] = head
    await fake_cache.put(ConfigEntityType.CATEGORY, "housing", {"code": "housing"})
    assert await category_read_use_cases.get_category_form(head.id) is None


@pytest.mark.asyncio
async def test_get_category_form_returns_none_when_bound_form_head_does_not_exist(
    fake_repo: FakeConfigHeadRepository,
    fake_cache: FakeSnapshotCache,
    category_read_use_cases: CategoryReadUseCases,
) -> None:
    head = _bare_head(ConfigEntityType.CATEGORY, "housing", current_version_id=uuid4())
    fake_repo.heads[(ConfigEntityType.CATEGORY, head.id)] = head
    await fake_cache.put(
        ConfigEntityType.CATEGORY,
        "housing",
        {"code": "housing", "form_definition_id": str(uuid4())},
    )
    assert await category_read_use_cases.get_category_form(head.id) is None
