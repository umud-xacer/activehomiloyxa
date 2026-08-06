"""Dispatcher redelivery of the same event is a no-op the second time (SAD Sec 11: "an event may
be delivered more than once, so consumers key on event identity"; Logical Sec 18 "idempotency is
data"). Proves the *effect* of replaying the same event twice equals the effect of once, via the
ProcessedEvent ledger + `idempotent_consume` -- not the dispatcher's own delivery guarantee
(that part is at-least-once by design, proven separately)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backbone.idempotency import idempotent_consume, make_processed_event_model
from backbone.outbox import OutboxDispatcher, make_outbox_event_model
from backbone.persistence import (
    AggregateMixin,
    make_engine,
    make_module_base,
    make_session_factory,
    session_scope,
)
from shared_kernel import EventEnvelope

# SideEffectRow/OutboxRow/ProcessedRow are dynamically synthesized ORM classes (fresh columns
# per test schema) -- there is no static type narrower than Any that describes them honestly.
Models = tuple[type[DeclarativeBase], Any, Any, Any]


@pytest.fixture
def models(scratch_schema: str) -> Models:
    base = make_module_base(scratch_schema)

    class SideEffectRow(base, AggregateMixin):  # type: ignore[misc,valid-type]
        """Stands in for "the local effect" a real consumer would apply exactly once --
        counting rows in this table is how the test observes how many times the handler's
        side effect actually landed."""

        __tablename__ = "side_effect"
        note: Mapped[str] = mapped_column(String(50))

    OutboxRow = make_outbox_event_model(base)
    ProcessedRow = make_processed_event_model(base)
    return base, SideEffectRow, OutboxRow, ProcessedRow


@pytest.fixture
async def prepared_schema(scratch_schema: str, models: Models) -> str:
    base, _, _, _ = models
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(base.metadata.create_all)
    await engine.dispose()
    return scratch_schema


@pytest.mark.asyncio
async def test_I13_replaying_the_same_event_twice_applies_the_side_effect_once(
    prepared_schema: str, models: Models
) -> None:
    _, SideEffectRow, _, ProcessedRow = models
    engine = make_engine()
    session_factory = make_session_factory(engine)

    event = EventEnvelope(
        event_id=uuid4(),
        event_type="DemoHappened",
        occurred_at=datetime.now(UTC),
        aggregate_type="DemoAggregate",
        aggregate_id=uuid4(),
        payload={"note": "x"},
    )

    async def consume_once() -> None:
        async with (
            session_scope(session_factory) as session,
            idempotent_consume(
                session, ProcessedRow, event_id=event.event_id, handler="side_effect_handler"
            ) as is_fresh,
        ):
            if is_fresh:
                session.add(SideEffectRow(note="applied"))

    # simulate at-least-once redelivery: the same event, handled twice.
    await consume_once()
    await consume_once()

    async with session_factory() as session:
        side_effects = (await session.execute(select(SideEffectRow))).scalars().all()
        ledger_rows = (await session.execute(select(ProcessedRow))).scalars().all()

    await engine.dispose()

    assert len(side_effects) == 1, "redelivery must not repeat the side effect"
    assert len(ledger_rows) == 1
    assert ledger_rows[0].event_id == event.event_id
    assert ledger_rows[0].handler == "side_effect_handler"


@pytest.mark.asyncio
async def test_I13_different_handlers_may_each_process_the_same_event_once(
    prepared_schema: str, models: Models
) -> None:
    """Composite PK (event_id, handler): two distinct consumers in the same module may both
    legitimately process one event -- only *redelivery to the same handler* is a no-op."""
    _, _, _, ProcessedRow = models
    engine = make_engine()
    session_factory = make_session_factory(engine)
    event_id = uuid4()

    async def consume_as(handler_name: str) -> bool:
        async with (
            session_scope(session_factory) as session,
            idempotent_consume(
                session, ProcessedRow, event_id=event_id, handler=handler_name
            ) as is_fresh,
        ):
            return is_fresh

    first = await consume_as("handler_a")
    second = await consume_as("handler_b")
    redelivered = await consume_as("handler_a")

    await engine.dispose()

    assert first is True
    assert second is True
    assert redelivered is False


@pytest.mark.asyncio
async def test_dispatcher_end_to_end_with_idempotent_handler(
    prepared_schema: str, models: Models
) -> None:
    """The dispatcher delivers at-least-once; the handler here is itself idempotent (via the
    ledger), so draining twice still applies the side effect once -- the two pieces composed
    together, matching how a real module wires them."""
    _, SideEffectRow, OutboxRow, ProcessedRow = models
    engine = make_engine()
    session_factory = make_session_factory(engine)

    aggregate_id = uuid4()
    async with session_scope(session_factory) as session:
        session.add(
            OutboxRow(
                id=uuid4(),
                event_type="DemoHappened",
                occurred_at=datetime.now(UTC),
                aggregate_type="DemoAggregate",
                aggregate_id=aggregate_id,
                payload={},
            )
        )

    async def idempotent_handler(event: EventEnvelope) -> None:
        async with (
            session_scope(session_factory) as session,
            idempotent_consume(
                session, ProcessedRow, event_id=event.event_id, handler="dispatcher_e2e"
            ) as is_fresh,
        ):
            if is_fresh:
                session.add(SideEffectRow(note="from dispatcher"))

    dispatcher = OutboxDispatcher(session_factory, OutboxRow, idempotent_handler)
    await dispatcher.drain_once()

    # simulate redelivery: reset the row back to PENDING (as if a retry/replay occurred) and
    # drain again -- the handler's own idempotency must still hold.
    async with session_factory() as session:
        row = (await session.execute(select(OutboxRow))).scalars().one()
        row.dispatch_status = "PENDING"
        await session.commit()

    await dispatcher.drain_once()

    async with session_factory() as session:
        side_effects = (await session.execute(select(SideEffectRow))).scalars().all()

    await engine.dispose()

    assert len(side_effects) == 1
