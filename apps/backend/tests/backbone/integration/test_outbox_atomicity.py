"""A state write and its outbox row commit in exactly one transaction (DEC-09: never
dual-write; Physical DB Sec 1.3 "Aggregate state + outbox: One transaction"). Against real
PostgreSQL -- SQLite or a mock session cannot prove real transactional rollback."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backbone.outbox import OutboxWriter, make_outbox_event_model
from backbone.persistence import (
    AggregateMixin,
    make_engine,
    make_module_base,
    make_session_factory,
    session_scope,
)
from shared_kernel import EventEnvelope

# DemoAggregate/OutboxRow are dynamically synthesized ORM classes (fresh columns per test
# schema) -- there is no static type narrower than Any that describes them honestly.
DemoModels = tuple[type[DeclarativeBase], Any, Any]


@pytest.fixture
def demo_models(scratch_schema: str) -> DemoModels:
    base = make_module_base(scratch_schema)

    class DemoAggregate(base, AggregateMixin):  # type: ignore[misc,valid-type]
        __tablename__ = "demo_aggregate"
        name: Mapped[str] = mapped_column(String(50))

    OutboxRow = make_outbox_event_model(base)
    return base, DemoAggregate, OutboxRow


@pytest.fixture
async def prepared_schema(scratch_schema: str, demo_models: DemoModels) -> str:
    base, _, _ = demo_models
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(base.metadata.create_all)
    await engine.dispose()
    return scratch_schema


@pytest.mark.asyncio
async def test_I12_state_and_outbox_row_commit_together(
    prepared_schema: str, demo_models: DemoModels
) -> None:
    _, DemoAggregate, OutboxRow = demo_models
    engine = make_engine()
    session_factory = make_session_factory(engine)
    agg_id = uuid4()

    async with session_scope(session_factory) as session:
        session.add(DemoAggregate(id=agg_id, name="hello"))
        writer = OutboxWriter(session, OutboxRow)
        await writer.append(
            EventEnvelope(
                event_id=uuid4(),
                event_type="DemoCreated",
                occurred_at=datetime.now(UTC),
                aggregate_type="DemoAggregate",
                aggregate_id=agg_id,
                payload={"name": "hello"},
            )
        )

    async with session_factory() as session:
        aggs = (await session.execute(select(DemoAggregate))).scalars().all()
        outbox_rows = (await session.execute(select(OutboxRow))).scalars().all()

    await engine.dispose()

    assert len(aggs) == 1
    assert len(outbox_rows) == 1
    assert outbox_rows[0].aggregate_id == agg_id
    assert outbox_rows[0].dispatch_status == "PENDING"


@pytest.mark.asyncio
async def test_I12_forced_failure_after_state_write_rolls_back_both(
    prepared_schema: str, demo_models: DemoModels
) -> None:
    """# enforces the checklist: "an injected failure after the state write but before commit
    rolls back both"."""
    _, DemoAggregate, OutboxRow = demo_models
    engine = make_engine()
    session_factory = make_session_factory(engine)
    agg_id = uuid4()

    class InjectedFailure(Exception):
        pass

    with pytest.raises(InjectedFailure):
        async with session_scope(session_factory) as session:
            session.add(DemoAggregate(id=agg_id, name="should_not_persist"))
            writer = OutboxWriter(session, OutboxRow)
            await writer.append(
                EventEnvelope(
                    event_id=uuid4(),
                    event_type="DemoCreated",
                    occurred_at=datetime.now(UTC),
                    aggregate_type="DemoAggregate",
                    aggregate_id=agg_id,
                    payload={},
                )
            )
            raise InjectedFailure("simulated failure between write and commit")

    async with session_factory() as session:
        aggs = (
            (await session.execute(select(DemoAggregate).where(DemoAggregate.id == agg_id)))
            .scalars()
            .all()
        )
        outbox_rows = (
            (await session.execute(select(OutboxRow).where(OutboxRow.aggregate_id == agg_id)))
            .scalars()
            .all()
        )

    await engine.dispose()

    assert aggs == []
    assert outbox_rows == []
