"""admin/application -- `OperatorSessionUseCases`, backing admin's own sole owned datum (DDD Sec
5.12). No OpenAPI operation exists for this in v1 -- see `domain/operator_session.py`'s own
docstring."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from admin.application.ports import OperatorSessionRepository
from admin.domain import OperatorSessionContext
from shared_kernel import UserId


class OperatorSessionUseCases:
    def __init__(self, *, sessions: OperatorSessionRepository) -> None:
        self._sessions = sessions

    async def get_or_create(
        self, operator_user_id: UserId, *, now: datetime
    ) -> OperatorSessionContext:
        existing = await self._sessions.get_by_operator(operator_user_id)
        if existing is not None:
            return existing
        return await self._sessions.upsert(operator_user_id=operator_user_id, context={}, now=now)

    async def update_context(
        self, operator_user_id: UserId, *, context: dict[str, Any], now: datetime
    ) -> OperatorSessionContext:
        return await self._sessions.upsert(
            operator_user_id=operator_user_id, context=context, now=now
        )
