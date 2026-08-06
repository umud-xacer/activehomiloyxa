"""Full controlled-track (maker -> gate -> checker -> publish) and category/form-definition
bootstrap flows against real Postgres/Redis -- the same scenarios `smoke_api2.py` proved
ad hoc earlier this session, now as durable regression tests. Also the standing regression test
for the one-directional category<->form-definition relationship bug fixed this session."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from apps.backend.tests.configuration.conftest import minimal_content
from apps.backend.tests.configuration.integration.conftest import (
    OpenCategoryReadUseCases,
    OpenUseCases,
)

from configuration.domain import ApproverPermissionError, SelfApprovalError
from configuration.domain.entity_types import ConfigEntityType
from configuration.domain.lifecycle import VersionStatus

MAKER = uuid4()
CHECKER = uuid4()


@pytest.mark.asyncio
async def test_role_definition_controlled_track_full_round_trip(
    open_use_cases: OpenUseCases,
) -> None:
    now = datetime.now(UTC)
    async with open_use_cases() as use_cases:
        head, version = await use_cases.create_draft(
            ConfigEntityType.ROLE_DEFINITION,
            code="content-editor",
            business_owner="Super Administrator",
            definition=minimal_content("role-definition"),
            actor_id=MAKER,
            now=now,
        )

    async with open_use_cases() as use_cases:
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

    with pytest.raises(SelfApprovalError):
        async with open_use_cases() as use_cases:
            await use_cases.publish(
                ConfigEntityType.ROLE_DEFINITION,
                head.id,
                version.id,
                actor_id=MAKER,
                actor_permission_keys=frozenset(
                    {"config:role-definition:manage", "config:role-definition:approve"}
                ),
                approval_note="self",
                now=now,
            )

    with pytest.raises(ApproverPermissionError):
        async with open_use_cases() as use_cases:
            await use_cases.publish(
                ConfigEntityType.ROLE_DEFINITION,
                head.id,
                version.id,
                actor_id=CHECKER,
                actor_permission_keys=frozenset({"config:role-definition:manage"}),
                approval_note="missing approve key",
                now=now,
            )

    async with open_use_cases() as use_cases:
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


@pytest.mark.asyncio
async def test_category_bootstraps_from_a_standalone_form_definition(
    open_use_cases: OpenUseCases, open_category_read_use_cases: OpenCategoryReadUseCases
) -> None:
    """Regression test: `FormDefinitionContent` carries no `category_id` (fixed this session --
    Physical DB Sec 2.4 has no promoted columns for `form_definition`/`_version` at all), so a
    form must be publishable entirely on its own, before any category exists to bind it."""
    now = datetime.now(UTC)

    async with open_use_cases() as use_cases:
        form_head, form_version = await use_cases.create_draft(
            ConfigEntityType.FORM_DEFINITION,
            code="housing-form",
            business_owner="Product Owner",
            definition=minimal_content("form-definition"),
            actor_id=MAKER,
            now=now,
        )
    async with open_use_cases() as use_cases:
        await use_cases.publish(
            ConfigEntityType.FORM_DEFINITION,
            form_head.id,
            form_version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({"config:form-definition:manage"}),
            approval_note="submit",
            now=now,
        )
    async with open_use_cases() as use_cases:
        form_published = await use_cases.publish(
            ConfigEntityType.FORM_DEFINITION,
            form_head.id,
            form_version.id,
            actor_id=CHECKER,
            actor_permission_keys=frozenset(
                {"config:form-definition:manage", "config:form-definition:approve"}
            ),
            approval_note="approved",
            now=now,
        )
    assert form_published.status is VersionStatus.PUBLISHED

    async with open_use_cases() as use_cases:
        cat_head, cat_version = await use_cases.create_draft(
            ConfigEntityType.CATEGORY,
            code="housing",
            business_owner="Product Owner",
            definition=minimal_content(
                "category", form_definition_id=form_head.id, tree_status="ACTIVE"
            ),
            actor_id=MAKER,
            now=now,
        )
    async with open_use_cases() as use_cases:
        await use_cases.publish(
            ConfigEntityType.CATEGORY,
            cat_head.id,
            cat_version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({"config:category:manage"}),
            approval_note="submit",
            now=now,
        )
    async with open_use_cases() as use_cases:
        cat_published = await use_cases.publish(
            ConfigEntityType.CATEGORY,
            cat_head.id,
            cat_version.id,
            actor_id=CHECKER,
            actor_permission_keys=frozenset({"config:category:manage", "config:category:approve"}),
            approval_note="approved",
            now=now,
        )
    assert cat_published.status is VersionStatus.PUBLISHED

    async with open_category_read_use_cases() as reads:
        categories = await reads.list_categories(parent_id=None, include_retired=False)
        assert any(c["id"] == str(cat_head.id) for c in categories)

        form_snapshot = await reads.get_category_form(cat_head.id)
        assert form_snapshot is not None
        assert form_snapshot["id"] == str(form_head.id)
