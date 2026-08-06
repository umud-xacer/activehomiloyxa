"""OutboxPort -- pure interface (typing.Protocol), no implementation shipped here."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from shared_kernel import EventEnvelope, OutboxPort


def test_is_a_protocol() -> None:
    assert getattr(OutboxPort, "_is_protocol", False) is True


def test_append_is_a_coroutine_method() -> None:
    assert inspect.iscoroutinefunction(OutboxPort.append)


def test_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        OutboxPort()  # type: ignore[misc]


class _FakeOutbox:
    """A minimal conforming implementation, used only to prove the Protocol is satisfiable by
    duck typing -- not a real adapter (that's persistence-backbone work, out of scope here)."""

    def __init__(self) -> None:
        self.appended: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.appended.append(event)


def test_a_conforming_class_is_recognised_via_isinstance() -> None:
    assert isinstance(_FakeOutbox(), OutboxPort)


def test_a_non_conforming_class_is_not_recognised() -> None:
    class NotAnOutbox:
        pass

    assert not isinstance(NotAnOutbox(), OutboxPort)


@pytest.mark.asyncio
async def test_append_stages_the_event() -> None:
    fake = _FakeOutbox()
    event = EventEnvelope(
        event_id=uuid4(),
        event_type="Test",
        occurred_at=datetime.now(UTC),
        aggregate_type="TestAggregate",
        aggregate_id=uuid4(),
        payload={},
    )
    await fake.append(event)
    assert fake.appended == [event]
