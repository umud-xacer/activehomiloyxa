"""`OperatorSessionUseCases` -- admin's own sole owned datum (DDD Sec 5.12)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from admin.application.operator_session_use_cases import OperatorSessionUseCases
from shared_kernel import UserId

from .conftest import FakeOperatorSessionRepository

_NOW = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)


async def test_get_or_create_creates_an_empty_context_on_first_call(
    fake_operator_sessions: FakeOperatorSessionRepository,
) -> None:
    operator_id = UserId(value=uuid4())
    use_cases = OperatorSessionUseCases(sessions=fake_operator_sessions)

    context = await use_cases.get_or_create(operator_id, now=_NOW)

    assert context.operator_user_id == operator_id
    assert context.context == {}


async def test_get_or_create_returns_the_same_row_on_a_second_call(
    fake_operator_sessions: FakeOperatorSessionRepository,
) -> None:
    operator_id = UserId(value=uuid4())
    use_cases = OperatorSessionUseCases(sessions=fake_operator_sessions)

    first = await use_cases.get_or_create(operator_id, now=_NOW)
    second = await use_cases.get_or_create(operator_id, now=_NOW.replace(hour=10))

    assert second.id == first.id
    assert second.updated_at == first.updated_at, "get_or_create must not touch an existing row"


async def test_update_context_replaces_the_stored_state(
    fake_operator_sessions: FakeOperatorSessionRepository,
) -> None:
    operator_id = UserId(value=uuid4())
    use_cases = OperatorSessionUseCases(sessions=fake_operator_sessions)
    await use_cases.get_or_create(operator_id, now=_NOW)

    later = _NOW.replace(hour=11)
    updated = await use_cases.update_context(
        operator_id, context={"queueFilter": "OPEN"}, now=later
    )

    assert updated.context == {"queueFilter": "OPEN"}
    assert updated.updated_at == later

    reloaded = await fake_operator_sessions.get_by_operator(operator_id)
    assert reloaded is not None
    assert reloaded.context == {"queueFilter": "OPEN"}
