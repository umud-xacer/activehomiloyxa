"""`SqlalchemyOperatorSessionRepository` against real Postgres -- proves the `UNIQUE
operator_user_id` upsert-by-operator semantics `admin.operator_session_context`'s own physical
schema and `repository.py`'s own docstring both promise."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from admin.infrastructure.persistence.repository import SqlalchemyOperatorSessionRepository
from shared_kernel import UserId

_NOW = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)


async def test_upsert_then_get_by_operator_round_trips(db_session: AsyncSession) -> None:
    repo = SqlalchemyOperatorSessionRepository(db_session)
    operator_id = UserId(value=uuid4())

    created = await repo.upsert(operator_user_id=operator_id, context={"page": 1}, now=_NOW)
    await db_session.commit()

    fetched = await repo.get_by_operator(operator_id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.operator_user_id == operator_id
    assert fetched.context == {"page": 1}


async def test_get_by_operator_returns_none_for_an_unknown_operator(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyOperatorSessionRepository(db_session)
    assert await repo.get_by_operator(UserId(value=uuid4())) is None


async def test_upsert_is_one_row_per_operator_not_a_second_insert(
    db_session: AsyncSession,
) -> None:
    """The physical schema's own `UNIQUE operator_user_id` constraint: a second `upsert` for the
    same operator must update the existing row, never fail on a duplicate key or create a second
    row."""
    repo = SqlalchemyOperatorSessionRepository(db_session)
    operator_id = UserId(value=uuid4())

    first = await repo.upsert(operator_user_id=operator_id, context={"page": 1}, now=_NOW)
    await db_session.commit()

    later = _NOW.replace(hour=10)
    second = await repo.upsert(operator_user_id=operator_id, context={"page": 2}, now=later)
    await db_session.commit()

    assert second.id == first.id, "upsert for an existing operator must update the same row"

    fetched = await repo.get_by_operator(operator_id)
    assert fetched is not None
    assert fetched.context == {"page": 2}
    assert fetched.updated_at == later
