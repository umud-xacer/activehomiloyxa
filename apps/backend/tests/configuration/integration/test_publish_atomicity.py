"""I-22: "Every administrative ... configuration action yields an immutable AuditEntry" -- in
scope for P-04, this is proven as the transactional-outbox half (analytics/BC-13's own consumer
is a later task): a successful publish's state write and its `ConfigurationChanged` outbox event
commit in exactly one transaction, against real PostgreSQL (DEC-09: never dual-write)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from apps.backend.tests.configuration.conftest import minimal_content
from apps.backend.tests.configuration.integration.conftest import OpenSession, OpenUseCases
from sqlalchemy import select

from configuration.application.exceptions import GateFailedError
from configuration.domain.entity_types import ConfigEntityType
from configuration.infrastructure.persistence.models import (
    OutboxEvent,
    SearchConfigurationVersion,
)

MAKER = uuid4()


@pytest.mark.asyncio
async def test_I22_publish_writes_state_and_outbox_event_in_one_transaction(
    open_use_cases: OpenUseCases, open_session: OpenSession
) -> None:
    now = datetime.now(UTC)
    async with open_use_cases() as use_cases:
        head, version = await use_cases.create_draft(
            ConfigEntityType.SEARCH_CONFIGURATION,
            code="search-default",
            business_owner="Product Owner",
            definition=minimal_content("search-configuration"),
            actor_id=MAKER,
            now=now,
        )

    async with open_use_cases() as use_cases:
        published = await use_cases.publish(
            ConfigEntityType.SEARCH_CONFIGURATION,
            head.id,
            version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({"config:search-configuration:manage"}),
            approval_note=None,
            now=now,
        )

    async with open_session() as session:
        row = (
            await session.execute(
                select(SearchConfigurationVersion).where(
                    SearchConfigurationVersion.id == published.id
                )
            )
        ).scalar_one()
        assert row.status == "PUBLISHED"

        outbox_rows = (
            (
                await session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == head.id  # type: ignore[attr-defined]
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(outbox_rows) == 1
    assert outbox_rows[0].event_type == "SearchConfigurationChanged"  # type: ignore[attr-defined]
    assert outbox_rows[0].aggregate_type == "search-configuration"  # type: ignore[attr-defined]
    assert outbox_rows[0].dispatch_status == "PENDING"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_I22_gate_rejected_publish_writes_no_outbox_event(
    open_use_cases: OpenUseCases, open_session: OpenSession
) -> None:
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

    async with open_use_cases() as use_cases:
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

    async with open_session() as session:
        outbox_rows = (
            (
                await session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == head.id  # type: ignore[attr-defined]
                    )
                )
            )
            .scalars()
            .all()
        )
        version_row = (
            await session.execute(
                select(SearchConfigurationVersion).where(
                    SearchConfigurationVersion.id == version.id
                )
            )
        ).scalar_one()

    assert outbox_rows == []
    assert version_row.status == "DRAFT"
