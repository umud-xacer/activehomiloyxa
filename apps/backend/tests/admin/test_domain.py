"""`OperatorSessionContext` -- admin's sole owned datum (DDD Sec 5.12)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from admin.domain import OperatorSessionContext
from shared_kernel import UserId

_NOW = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)


def test_create_assigns_a_fresh_id_and_the_given_context() -> None:
    operator_id = UserId(value=uuid4())
    context = OperatorSessionContext.create(
        operator_user_id=operator_id, context={"queueFilter": "OPEN"}, now=_NOW
    )
    assert context.operator_user_id == operator_id
    assert context.context == {"queueFilter": "OPEN"}
    assert context.updated_at == _NOW


def test_with_context_replaces_the_stored_state_wholesale_and_keeps_identity() -> None:
    operator_id = UserId(value=uuid4())
    original = OperatorSessionContext.create(
        operator_user_id=operator_id, context={"queueFilter": "OPEN", "page": 1}, now=_NOW
    )
    later = _NOW.replace(hour=10)

    updated = original.with_context(context={"page": 2}, now=later)

    assert updated.id == original.id
    assert updated.operator_user_id == operator_id
    assert updated.context == {"page": 2}, "with_context replaces, it does not merge"
    assert updated.updated_at == later
