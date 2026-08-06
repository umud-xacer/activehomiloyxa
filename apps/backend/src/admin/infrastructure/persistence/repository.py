"""`SqlalchemyOperatorSessionRepository` -- implements `application.ports.
OperatorSessionRepository` against Postgres. `upsert` is a real upsert (not a plain `add`) --
one row per operator (`UNIQUE operator_user_id`), matching admin's own work-session semantics
(the latest write wins; there is no history to preserve)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.domain import OperatorSessionContext
from admin.infrastructure.persistence.models import OperatorSessionContextRow
from shared_kernel import UserId


def _row_to_domain(row: OperatorSessionContextRow) -> OperatorSessionContext:
    return OperatorSessionContext(
        id=row.id,
        operator_user_id=UserId(value=row.operator_user_id),
        context=row.context,
        updated_at=row.updated_at,
    )


class SqlalchemyOperatorSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_operator(self, operator_user_id: UserId) -> OperatorSessionContext | None:
        result = await self._session.execute(
            select(OperatorSessionContextRow).where(
                OperatorSessionContextRow.operator_user_id == operator_user_id.value
            )
        )
        row = result.scalar_one_or_none()
        return _row_to_domain(row) if row is not None else None

    async def upsert(
        self, *, operator_user_id: UserId, context: dict[str, Any], now: datetime
    ) -> OperatorSessionContext:
        result = await self._session.execute(
            select(OperatorSessionContextRow).where(
                OperatorSessionContextRow.operator_user_id == operator_user_id.value
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = OperatorSessionContextRow(
                id=uuid4(),
                operator_user_id=operator_user_id.value,
                context=context,
                updated_at=now,
            )
            self._session.add(row)
        else:
            row.context = context
            row.updated_at = now
        await self._session.flush()
        return _row_to_domain(row)
