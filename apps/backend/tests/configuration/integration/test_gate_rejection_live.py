"""Config Framework Sec 9: "A change failing any check is refused with a precise reason; it
stays in Draft/Validation and is never published" -- proven against real Postgres because it
depends on transaction-commit behaviour a fake repository cannot exercise (a fake never rolls
back on a raised exception; a real `session_scope` does)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from apps.backend.tests.configuration.conftest import minimal_content
from apps.backend.tests.configuration.integration.conftest import OpenSession, OpenUseCases
from sqlalchemy import delete, select

from configuration.application.exceptions import GateFailedError
from configuration.domain.entity_types import ConfigEntityType
from configuration.domain.lifecycle import VersionStatus
from configuration.infrastructure.persistence.models import (
    PermissionGroup,
    RoleDefinitionVersion,
)

MAKER = uuid4()
CHECKER = uuid4()


@pytest.mark.asyncio
async def test_promoted_column_check_constraint_blocks_saving_a_gate_rejectable_draft(
    open_use_cases: OpenUseCases,
) -> None:
    """`search_configuration_version` has a DB-level `CHECK (promotion_page_cap >= 0)`
    (`infrastructure/persistence/models.py` `SearchConfigurationVersion.__table_args__`) that
    would otherwise fire at `create_draft` time -- before the gate (`domain/gate.py`'s own
    `CONFLICTING_RULE` check for the exact same rule) ever runs. Config Framework Sec 9 assumes
    a maker can always *save* a draft with bad content and get a precise, structured rejection
    at validate/submit time (`GateFailedError` -> a 422 Problem), not a raw, unmapped
    `sqlalchemy.exc.IntegrityError` (an unhandled 500 at the API layer).

    `role_definition_version.permission_keys` already had a workaround for exactly this class
    of problem (`repository.py`'s `_extra_version_columns`:
    `"permission_keys": content.get("permission_keys") or ["__draft__"]`, satisfying its own
    `CHECK (cardinality(permission_keys) > 0)` for group/parent-only roles); the same treatment
    is now extended to `search_configuration_version.promotion_page_cap` and
    `product_definition_version.price_amount` -- the promoted column gets a safe sentinel while
    `definition_document` (what the gate actually inspects) keeps the true, invalid value."""
    now = datetime.now(UTC)
    async with open_use_cases() as use_cases:
        head, version = await use_cases.create_draft(
            ConfigEntityType.SEARCH_CONFIGURATION,
            code="search-broken-promoted-column",
            business_owner="Product Owner",
            definition=minimal_content("search-configuration", promotion_page_cap=-1),
            actor_id=MAKER,
            now=now,
        )

    with pytest.raises(GateFailedError):
        async with open_use_cases() as use_cases:
            await use_cases.publish(
                ConfigEntityType.SEARCH_CONFIGURATION,
                head.id,
                version.id,
                actor_id=MAKER,
                actor_permission_keys=frozenset({"config:search-configuration:manage"}),
                approval_note=None,
                now=now,
            )


@pytest.mark.asyncio
async def test_promoted_price_amount_handles_string_and_negative_values(
    open_use_cases: OpenUseCases,
) -> None:
    """`product_definition_version.price_amount` has the same class of promoted-column CHECK
    (`price_amount >= 0`) as `promotion_page_cap` above, plus an extra wrinkle: this codebase's
    convention encodes money as a decimal-string (`"10.00"`, see `minimal_content`), which a
    naive `isinstance(value, int | float | Decimal)` guard would treat as always-invalid and
    silently zero out even for perfectly valid drafts. Proves both: a valid string amount is
    saved as-is, and a negative amount saves cleanly but is rejected by the gate at submit."""
    now = datetime.now(UTC)
    async with open_use_cases() as use_cases:
        head, version = await use_cases.create_draft(
            ConfigEntityType.PRODUCT_DEFINITION,
            code="product-negative-price",
            business_owner="Product Owner",
            definition=minimal_content("product-definition", price_amount="-5.00"),
            actor_id=MAKER,
            now=now,
        )

    with pytest.raises(GateFailedError):
        async with open_use_cases() as use_cases:
            await use_cases.publish(
                ConfigEntityType.PRODUCT_DEFINITION,
                head.id,
                version.id,
                actor_id=MAKER,
                actor_permission_keys=frozenset({"config:product-definition:manage"}),
                approval_note=None,
                now=now,
            )


@pytest.mark.asyncio
async def test_gate_rejection_on_maker_submit_persists_draft_status(
    open_use_cases: OpenUseCases,
) -> None:
    """`default_sort` must be one of `sort_options` (CONFLICTING_RULE) -- a pure gate-level
    business rule with no corresponding promoted column/DB CHECK constraint, unlike
    `promotion_page_cap` (see the KNOWN BUG note on `test_promoted_column_check_constraint_...`
    below): the draft must be *saveable* first so the gate can reject it cleanly at submit time."""
    now = datetime.now(UTC)
    async with open_use_cases() as use_cases:
        head, version = await use_cases.create_draft(
            ConfigEntityType.SEARCH_CONFIGURATION,
            code="search-broken",
            business_owner="Product Owner",
            definition=minimal_content(
                "search-configuration",
                sort_options=["RECENCY"],
                default_sort="RELEVANCE",
            ),
            actor_id=MAKER,
            now=now,
        )

    with pytest.raises(GateFailedError):
        async with open_use_cases() as use_cases:
            await use_cases.publish(
                ConfigEntityType.SEARCH_CONFIGURATION,
                head.id,
                version.id,
                actor_id=MAKER,
                actor_permission_keys=frozenset({"config:search-configuration:manage"}),
                approval_note=None,
                now=now,
            )

    async with open_use_cases() as use_cases:
        reloaded = await use_cases.get_version(
            ConfigEntityType.SEARCH_CONFIGURATION, head.id, version.id
        )
    assert reloaded.status is VersionStatus.DRAFT


@pytest.mark.asyncio
async def test_checker_gate_rejection_does_not_persist_draft_reversion(
    open_use_cases: OpenUseCases, open_session: OpenSession
) -> None:
    """`use_cases.publish()`'s checker-call gate-failure branch calls
    `version.return_to_draft_after_failed_gate()` and persists it via `update_version` *before*
    raising `GateFailedError`. That raise unwinds out through the composition root
    (`main.py` -> `composition_root.provide_configuration_use_cases`), which previously rolled
    back the *entire* transaction on any exception, including the "reverted to Draft" write the
    use case just made -- leaving the version stuck at APPROVAL/VALIDATION, not DRAFT as Config
    Framework Sec 9 intends ("it stays in Draft/Validation"), with no way for the maker to
    re-submit a fix (a subsequent `publish()` call would take the checker-call branch again,
    since status was still APPROVAL). Fixed in `composition_root.provide_configuration_use_cases`
    (and mirrored in this file's `open_use_cases` fixture): a `GateFailedError` now commits
    before re-propagating, since a gate-failure outcome is a normal business result, not a
    transaction-aborting error.

    Reproduced here with a permission-group dependency that exists at the maker's submit time
    (gate passes, moves to APPROVAL) and is removed before the checker's re-validation call
    (Config Framework Sec 2.6: "re-run on rollback" applies the same re-validate-on-re-entry
    discipline to the checker's call) -- the same race the re-validation exists to catch.
    """
    now = datetime.now(UTC)
    async with open_session() as session:
        session.add(
            PermissionGroup(
                id=uuid4(),
                code="moderators",
                name="Moderators",
                permission_keys=["config:notification-template:manage"],
                created_at=now,
                created_by=MAKER,
                updated_at=now,
                updated_by=MAKER,
            )
        )

    async with open_use_cases() as use_cases:
        head, version = await use_cases.create_draft(
            ConfigEntityType.ROLE_DEFINITION,
            code="probe-role",
            business_owner="Owner",
            definition=minimal_content(
                "role-definition",
                permission_keys=[],
                permission_group_codes=["moderators"],
            ),
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
            approval_note="submit",
            now=now,
        )
    assert after_maker.status is VersionStatus.APPROVAL

    async with open_session() as session:
        await session.execute(delete(PermissionGroup).where(PermissionGroup.code == "moderators"))

    with pytest.raises(GateFailedError):
        async with open_use_cases() as use_cases:
            await use_cases.publish(
                ConfigEntityType.ROLE_DEFINITION,
                head.id,
                version.id,
                actor_id=CHECKER,
                actor_permission_keys=frozenset(
                    {"config:role-definition:manage", "config:role-definition:approve"}
                ),
                approval_note="approve",
                now=now,
            )

    async with open_session() as session:
        row = (
            await session.execute(
                select(RoleDefinitionVersion).where(RoleDefinitionVersion.id == version.id)
            )
        ).scalar_one()

    assert row.status == "DRAFT"
